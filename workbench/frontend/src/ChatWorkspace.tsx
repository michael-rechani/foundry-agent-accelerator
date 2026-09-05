import { useEffect, useRef, useState } from 'react'
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUp,
  Check,
  ChevronDown,
  CircleAlert,
  Clock3,
  FileCheck2,
  FlaskConical,
  GitBranch,
  History,
  Layers3,
  LayoutGrid,
  LoaderCircle,
  LockKeyhole,
  MessageSquare,
  Plus,
  Save,
  Search,
  ShieldCheck,
  Square,
  Trash2,
  X,
} from 'lucide-react'
import '@fontsource-variable/manrope'
import '@fontsource/ibm-plex-mono/400.css'
import './chat.css'
import { useHistoryClient } from './history-client'
import { ConversationTurn } from './ConversationTurn'
import type { Turn } from './conversation-types'
import { requestJson } from './request'
import { WaitingIndicator } from './WaitingIndicator'

type Agent = {
  id: string
  label: string
  category: string
  description: string
  agent: string
  tools: Record<string, string>
}
type Config = {
  mode: 'preview' | 'private'
  agents: Agent[]
  max_characters: number
  history_enabled: boolean
}
type Measurement = {
  id: string
  agent: string
  outcome: 'completed' | 'failed' | 'stopped'
  duration: number
}
type View = 'chat' | 'catalog' | 'performance' | 'history'
type SavedChat = {
  id: string
  title: string
  agent_id: string
  updated_at: string
}
type SavedVersion = { id: string; _etag: string }

const prompts = [
  {
    label: 'Review an application',
    text: 'Review this synthetic application against the criteria. Cite identifiers and distinguish missing evidence from noncompliance.\n\nCRIT-1: Include a project budget.\nCRIT-2: Identify a delivery timeline.\nAPP-1: Twelve weekly workshops starting October 1, led by a program lead and two facilitators. No budget is supplied.',
  },
  {
    label: 'Check a case record',
    text: 'Review these synthetic case records for conflicting dates and missing evidence. Cite records without choosing an unsupported date.\n\nCASE-1: Intake completed June 1, follow-up June 10.\nCASE-2: Intake completed June 3, follow-up June 10.\nCASE-3: Undated follow-up; a supporting document is outstanding.',
  },
  {
    label: 'Start with a question',
    text: 'I need a review. What information should I provide?',
  },
]
const errors: Record<string, string> = {
  preview_only:
    'This local preview is not connected to Foundry. No agent was invoked.',
  busy: 'The workbench is at capacity. Try again shortly.',
  timeout:
    'The request timed out. Remote work may still finish; check before retrying.',
  backend_unavailable:
    'Foundry could not complete this request. Check private connectivity and managed-identity access.',
  incomplete_response: 'The agent did not return a completed response.',
  request_too_large:
    'The conversation exceeds 64 KiB. Start a new chat or shorten your message.',
  invalid_request:
    'The conversation was not accepted. Check its length and selected agent.',
  request_not_allowed: 'This browser origin is not permitted.',
}

export default function ChatWorkspace() {
  const [config, setConfig] = useState<Config | null>(null)
  const [selected, setSelected] = useState('')
  const [view, setView] = useState<View>('chat')
  const [draft, setDraft] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [pending, setPending] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [query, setQuery] = useState('')
  const [measurements, setMeasurements] = useState<Measurement[]>([])
  const [saved, setSaved] = useState<SavedVersion | null>(null)
  const [dirty, setDirty] = useState(false)
  const [historyBusy, setHistoryBusy] = useState(false)
  const [savedChats, setSavedChats] = useState<SavedChat[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const historyRequest = useHistoryClient()
  const controller = useRef<AbortController | null>(null)
  const editor = useRef<HTMLTextAreaElement>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const agent = config?.agents.find((item) => item.id === selected)
  const history = turns.flatMap((turn) => [
    { role: 'user', content: turn.question },
    { role: 'assistant', content: turn.result.text },
  ])
  const characters =
    history.reduce((total, message) => total + message.content.length, 0) +
    draft.length
  const payload = JSON.stringify({ agent_id: selected, input: draft, history })
  const exceedsLimit =
    characters > (config?.max_characters || 60000) ||
    new TextEncoder().encode(payload).length > 65536 ||
    turns.length > 10
  const completed = measurements.filter((item) => item.outcome === 'completed')
  const average = completed.length
    ? completed.reduce((total, item) => total + item.duration, 0) /
      completed.length
    : null
  const unsaved = dirty || !!draft || busy

  useEffect(() => {
    if (!unsaved) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [unsaved])

  useEffect(() => {
    const abort = new AbortController()
    fetch('/api/config', { signal: abort.signal })
      .then(async (response) => {
        if (!response.ok)
          throw new Error(
            'Workspace configuration unavailable. Reload to try again.',
          )
        const value: Config = await response.json()
        setConfig(value)
        setSelected(value.agents[0]?.id || '')
      })
      .catch((problem) => {
        if (problem.name !== 'AbortError') setError(problem.message)
      })
    return () => {
      abort.abort()
      controller.current?.abort()
    }
  }, [])

  useEffect(() => {
    if (view === 'chat') bottom.current?.scrollIntoView({ block: 'end' })
  }, [turns, busy, view])

  async function submit() {
    if (!agent || !draft.trim() || busy || historyBusy || exceedsLimit) return
    const question = draft
    const abort = new AbortController()
    const started = performance.now()
    const measurementId = crypto.randomUUID()
    controller.current = abort
    setBusy(true)
    setError('')
    setNotice('')
    setPending(question)
    const timeout = window.setTimeout(() => abort.abort(), 190000)
    try {
      const { response, data } = await requestJson(
        '/api/reviews',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Workbench-Request': '1',
          },
          body: payload,
        },
        abort.signal,
      )
      if (!response.ok)
        throw new Error(
          `${errors[data.error] || 'Request failed.'}${data.request_id ? ` Reference: ${data.request_id}` : ''}`,
        )
      setTurns((previous) => [...previous, { question, result: data }])
      setDirty(true)
      setDraft('')
      setPending('')
      if (config?.mode === 'private')
        setMeasurements((previous) => [
          ...previous,
          {
            id: measurementId,
            agent: agent.label,
            outcome: 'completed',
            duration: performance.now() - started,
          },
        ])
    } catch (problem) {
      setError(
        abort.signal.aborted
          ? 'Stopped waiting. Remote work may continue; no automatic retry was made.'
          : problem instanceof Error
            ? problem.message
            : 'Request failed.',
      )
      if (config?.mode === 'private')
        setMeasurements((previous) => [
          ...previous,
          {
            id: measurementId,
            agent: agent.label,
            outcome: abort.signal.aborted ? 'stopped' : 'failed',
            duration: performance.now() - started,
          },
        ])
    } finally {
      window.clearTimeout(timeout)
      controller.current = null
      setBusy(false)
      editor.current?.focus()
    }
  }

  function newChat(agentId = selected) {
    if (busy || historyBusy) return
    if (
      (draft || dirty) &&
      !window.confirm('Start a new chat? Unsaved messages will be cleared.')
    )
      return
    setSelected(agentId)
    setTurns([])
    setDraft('')
    setPending('')
    setError('')
    setNotice('')
    setView('chat')
    setSaved(null)
    setDirty(false)
  }

  async function listHistory(more = false) {
    if (historyBusy) return
    setView('history')
    setHistoryBusy(true)
    setNotice('')
    try {
      const data = await historyRequest(
        more && cursor ? `?cursor=${encodeURIComponent(cursor)}` : '',
      )
      setSavedChats((previous) =>
        more ? [...previous, ...data.items] : data.items,
      )
      setCursor(data.cursor)
    } catch (problem) {
      setNotice(
        problem instanceof Error ? problem.message : 'History unavailable.',
      )
    } finally {
      setHistoryBusy(false)
    }
  }

  async function saveChat() {
    if (!turns.length || busy || historyBusy) return
    setHistoryBusy(true)
    try {
      const data = await historyRequest(saved ? `/${saved.id}` : '', {
        method: saved ? 'PUT' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(saved ? { 'If-Match': saved._etag } : {}),
        },
        body: JSON.stringify({
          agent_id: selected,
          turns: turns.map(({ question, result }) => ({ question, result })),
        }),
      })
      setSaved(data)
      setDirty(false)
      setNotice(
        'Completed replies saved to shared history for 30 days. Drafts are not saved.',
      )
    } catch (problem) {
      setNotice(problem instanceof Error ? problem.message : 'Save failed.')
    } finally {
      setHistoryBusy(false)
    }
  }

  async function openChat(item: SavedChat) {
    if (
      busy ||
      historyBusy ||
      ((dirty || draft) &&
        !window.confirm(
          'Open this conversation and discard unsaved local messages?',
        ))
    )
      return
    setHistoryBusy(true)
    try {
      const data = await historyRequest(`/${item.id}`)
      setSaved({ id: data.id, _etag: data._etag })
      setSelected(data.agent_id)
      setTurns(data.turns.map((turn: Turn) => ({ ...turn, stored: true })))
      setDirty(false)
      setDraft('')
      setPending('')
      setError('')
      setNotice('')
      setView('chat')
    } catch (problem) {
      setNotice(problem instanceof Error ? problem.message : 'Open failed.')
    } finally {
      setHistoryBusy(false)
    }
  }

  async function deleteChat(item: SavedChat) {
    if (
      busy ||
      historyBusy ||
      !window.confirm(
        'Delete this conversation from shared history for everyone?',
      )
    )
      return
    setHistoryBusy(true)
    try {
      const current = await historyRequest(`/${item.id}`)
      await historyRequest(`/${item.id}`, {
        method: 'DELETE',
        headers: { 'If-Match': current._etag },
      })
      setSavedChats((previous) =>
        previous.filter((chat) => chat.id !== item.id),
      )
      if (saved?.id === item.id) {
        setSaved(null)
        setDirty(turns.length > 0)
      }
      setNotice('Deleted from shared history.')
    } catch (problem) {
      setNotice(problem instanceof Error ? problem.message : 'Delete failed.')
    } finally {
      setHistoryBusy(false)
    }
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text)
      setNotice('Response copied.')
    } catch {
      setNotice('Clipboard unavailable. Select and copy the response manually.')
    }
  }

  function download() {
    const url = URL.createObjectURL(
      new Blob(
        [JSON.stringify({ agent: agent?.agent, turns, draft }, null, 2)],
        { type: 'application/json' },
      ),
    )
    const link = document.createElement('a')
    link.href = url
    link.download = 'foundry-conversation.json'
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="chat-app">
      <aside className="chat-sidebar">
        <div className="chat-brand">
          <Layers3 size={26} />
          <span>
            foundry<small>WORKBENCH</small>
          </span>
        </div>
        <button
          className="new-chat"
          disabled={busy || historyBusy}
          onClick={() => newChat()}
          title="New chat"
        >
          <Plus size={18} />
          <span>New chat</span>
        </button>
        <nav aria-label="Workspace">
          <button
            disabled={!config?.history_enabled || historyBusy}
            aria-current={view === 'history' ? 'page' : undefined}
            onClick={() => void listHistory()}
            title="Shared history"
          >
            <History size={18} />
            <span>Shared history</span>
          </button>
          <button
            aria-current={view === 'chat' ? 'page' : undefined}
            onClick={() => setView('chat')}
            title="Chat"
          >
            <MessageSquare size={18} />
            <span>Chat</span>
          </button>
          <button
            aria-current={view === 'catalog' ? 'page' : undefined}
            onClick={() => setView('catalog')}
            title="Agent catalog"
          >
            <LayoutGrid size={18} />
            <span>Agent catalog</span>
            <small>{config?.agents.length ?? 0}</small>
          </button>
          <button
            aria-current={view === 'performance' ? 'page' : undefined}
            onClick={() => setView('performance')}
            title="Performance"
          >
            <Activity size={18} />
            <span>Performance</span>
          </button>
        </nav>
        <div className="sidebar-session">
          <span className="micro-label">CURRENT CONVERSATION</span>
          <div>
            <span className="status-dot" />
            {agent?.label || 'Connecting'}
          </div>
          <small>
            {turns.length ? `${turns.length} replies` : 'New conversation'}
          </small>
        </div>
        <div className="chat-private">
          <LockKeyhole size={16} />
          <span>
            {config?.mode === 'private' ? 'Private workspace' : 'Local preview'}
            <small>
              {config?.mode === 'private'
                ? 'No user sign-in'
                : 'No Azure calls'}
            </small>
          </span>
        </div>
      </aside>

      <div className="chat-workspace">
        <header className="chat-topbar">
          <div className="view-title">
            {view === 'chat'
              ? 'Conversation'
              : view === 'catalog'
                ? 'Agent catalog'
                : view === 'history'
                  ? 'Shared history'
                  : 'Performance'}
            <span>/</span>
            <span>Workspace</span>
          </div>
          <div className="topbar-actions">
            <span
              className={`environment-badge ${config?.mode === 'private' ? 'private' : ''}`}
            >
              <span className="status-dot" />
              {config?.mode === 'private' ? 'PRIVATE' : 'PREVIEW'}
            </span>
            <button
              className="chat-icon"
              title="Save to shared history"
              aria-label="Save to shared history"
              disabled={
                !config?.history_enabled ||
                !turns.length ||
                busy ||
                historyBusy ||
                !dirty
              }
              onClick={() => void saveChat()}
            >
              {historyBusy ? (
                <LoaderCircle size={17} className="spin" />
              ) : (
                <Save size={17} />
              )}
            </button>
            <button
              className="chat-icon"
              title="Export conversation"
              aria-label="Export conversation"
              disabled={!turns.length && !draft}
              onClick={download}
            >
              <ArrowDownToLine size={17} />
            </button>
          </div>
        </header>

        {view === 'history' ? (
          <main className="secondary-view">
            <div className="section-heading">
              <span className="micro-label">
                SHARED WORKSPACE / 30-DAY RETENTION
              </span>
              <h1>Saved conversations</h1>
              <p>Visible to everyone with workspace access</p>
            </div>
            <div className="saved-list">
              {savedChats.map((item) => (
                <article key={item.id}>
                  <button
                    className="saved-open"
                    disabled={busy || historyBusy}
                    onClick={() => void openChat(item)}
                  >
                    <MessageSquare size={18} />
                    <span>
                      <strong>{item.title}</strong>
                      <small>
                        {
                          config?.agents.find(
                            (entry) => entry.id === item.agent_id,
                          )?.label
                        }{' '}
                        / {new Date(item.updated_at).toLocaleString()}
                      </small>
                    </span>
                  </button>
                  <button
                    className="chat-icon"
                    title="Delete shared conversation"
                    aria-label={`Delete ${item.title}`}
                    disabled={busy || historyBusy}
                    onClick={() => void deleteChat(item)}
                  >
                    <Trash2 size={16} />
                  </button>
                </article>
              ))}
            </div>
            {historyBusy ? (
              <p role="status">Loading history...</p>
            ) : !savedChats.length ? (
              <p className="no-data">No saved conversations</p>
            ) : null}
            {cursor && (
              <button
                className="history-more"
                disabled={historyBusy}
                onClick={() => void listHistory(true)}
              >
                Load more
              </button>
            )}
          </main>
        ) : view === 'chat' ? (
          <main className="conversation-view">
            <div className="conversation-heading">
              <button
                className="agent-picker"
                onClick={() => setView('catalog')}
              >
                <span className="agent-avatar">
                  <GitBranch size={18} />
                </span>
                <span>
                  {agent?.label || 'Connecting'}
                  <small>{agent?.category || 'Agent'}</small>
                </span>
                <ChevronDown size={14} />
              </button>
              <span className="memory-label">
                <ShieldCheck size={13} />
                {saved
                  ? dirty
                    ? 'Unsaved changes'
                    : draft
                      ? 'Draft not saved'
                      : 'Saved / shared'
                  : 'Not saved'}
              </span>
            </div>
            <div className="conversation-scroll" aria-label="Conversation">
              {!turns.length && !pending ? (
                <div className="chat-welcome">
                  <div className="welcome-art">
                    <MessageSquare size={38} strokeWidth={1.25} />
                    <span>
                      <Check size={14} />
                    </span>
                  </div>
                  <span className="micro-label">
                    A LITTLE CONTEXT. A CLEARER NEXT STEP.
                  </span>
                  <h1>What are we working on?</h1>
                  <p>{agent?.description || 'Connecting to your workspace'}</p>
                  <div className="prompt-options">
                    {prompts.map((prompt) => (
                      <button
                        key={prompt.label}
                        disabled={!config}
                        onClick={() => {
                          setDraft(prompt.text)
                          editor.current?.focus()
                        }}
                      >
                        <FlaskConical size={16} />
                        <span>{prompt.label}</span>
                        <ArrowRight size={15} />
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="message-list">
                  {turns.map((turn, index) => (
                    <ConversationTurn
                      key={`${turn.result.request_id}-${index}`}
                      turn={turn}
                      label={agent?.label}
                      onCopy={copy}
                    />
                  ))}
                  {pending && (
                    <article className="user-message">
                      <span className="message-author">You</span>
                      <p>{pending}</p>
                    </article>
                  )}
                </div>
              )}
              {busy && <WaitingIndicator label={agent?.label} />}
              {error && (
                <div className="chat-error" role="alert">
                  <CircleAlert size={19} />
                  <p>{error}</p>
                  <button
                    className="chat-icon"
                    aria-label="Dismiss error"
                    onClick={() => {
                      setError('')
                      setPending('')
                    }}
                  >
                    <X size={16} />
                  </button>
                </div>
              )}
              <div ref={bottom} />
            </div>
            <div className="composer-area">
              <form
                className={`composer ${exceedsLimit ? 'over-limit' : ''}`}
                onSubmit={(event) => {
                  event.preventDefault()
                  void submit()
                }}
              >
                <textarea
                  ref={editor}
                  aria-label="Message"
                  placeholder={`Message ${agent?.label || 'your agent'}...`}
                  value={draft}
                  disabled={busy}
                  rows={3}
                  maxLength={60000}
                  onChange={(event) => {
                    setDraft(event.target.value)
                    if (!busy) setPending('')
                  }}
                  onKeyDown={(event) => {
                    if (
                      event.key === 'Enter' &&
                      !event.shiftKey &&
                      !event.nativeEvent.isComposing
                    ) {
                      event.preventDefault()
                      void submit()
                    }
                  }}
                />
                <div className="composer-toolbar">
                  <span>
                    <LockKeyhole size={12} />
                    {config?.mode === 'private'
                      ? 'Synthetic data only'
                      : 'Preview / execution disabled'}
                  </span>
                  <div>
                    <span
                      className="context-count"
                      title="Conversation characters"
                    >
                      {characters.toLocaleString()} / 60,000
                    </span>
                    {busy ? (
                      <button
                        key="stop"
                        type="button"
                        className="send-button stop"
                        aria-label="Stop waiting"
                        title="Stop waiting"
                        onClick={(event) => {
                          event.preventDefault()
                          controller.current?.abort()
                        }}
                      >
                        <Square size={16} />
                      </button>
                    ) : (
                      <button
                        key="send"
                        type="submit"
                        className="send-button"
                        disabled={
                          !agent || !draft.trim() || exceedsLimit || historyBusy
                        }
                        aria-label="Send message"
                        title="Send message"
                      >
                        <ArrowUp size={20} />
                      </button>
                    )}
                  </div>
                </div>
              </form>
              {exceedsLimit ? (
                <p className="composer-warning" role="alert">
                  Conversation limit reached. Shorten your message or start a
                  new chat.
                </p>
              ) : (
                <div className="composer-footnote">
                  <span>FOUNDRY WORKBENCH</span>
                  <span>Evidence-grounded. Human-reviewed.</span>
                </div>
              )}
            </div>
          </main>
        ) : view === 'catalog' ? (
          <main className="secondary-view">
            <div className="section-heading">
              <span className="micro-label">YOUR WORKSPACE</span>
              <h1>Agent catalog</h1>
              <p>
                {config?.agents.length || 0} available{' '}
                {config?.agents.length === 1 ? 'agent' : 'agents'}
              </p>
            </div>
            <label className="catalog-search">
              <Search size={17} />
              <input
                aria-label="Search agents"
                placeholder="Search agents"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <div className="agent-grid">
              {config?.agents
                .filter((item) =>
                  `${item.label} ${item.description} ${item.category}`
                    .toLowerCase()
                    .includes(query.toLowerCase()),
                )
                .map((item) => (
                  <article className="catalog-agent" key={item.id}>
                    <div className="catalog-agent-top">
                      <span className="catalog-avatar">
                        {item.category === 'Coordinator' ? (
                          <GitBranch size={25} />
                        ) : (
                          <FileCheck2 size={25} />
                        )}
                      </span>
                      <span className="category-label">{item.category}</span>
                    </div>
                    <h2>{item.label}</h2>
                    <p>{item.description}</p>
                    <div className="catalog-capabilities">
                      <GitBranch size={13} />
                      {Object.keys(item.tools).length} specialist bindings
                    </div>
                    <button
                      className="catalog-select"
                      disabled={busy || historyBusy}
                      onClick={() =>
                        item.id === selected
                          ? setView('chat')
                          : newChat(item.id)
                      }
                    >
                      {item.id === selected ? 'Return to chat' : 'Start chat'}
                      <ArrowRight size={17} />
                    </button>
                  </article>
                ))}
            </div>
            {config &&
              !config.agents.some((item) =>
                `${item.label} ${item.description} ${item.category}`
                  .toLowerCase()
                  .includes(query.toLowerCase()),
              ) && <p className="no-data">No matching agents</p>}
          </main>
        ) : (
          <main className="secondary-view">
            <div className="section-heading">
              <span className="micro-label">THIS BROWSER SESSION</span>
              <h1>Performance</h1>
              <p>Observed requests / end-to-end duration</p>
            </div>
            <div className="metric-strip">
              <div>
                <MessageSquare size={18} />
                <span>Completed</span>
                <strong>{completed.length}</strong>
              </div>
              <div>
                <Clock3 size={18} />
                <span>Average response</span>
                <strong>
                  {average === null
                    ? 'Not available'
                    : `${(average / 1000).toFixed(1)}s`}
                </strong>
              </div>
              <div>
                <CircleAlert size={18} />
                <span>Failed / stopped</span>
                <strong>
                  {
                    measurements.filter((item) => item.outcome === 'failed')
                      .length
                  }{' '}
                  /{' '}
                  {
                    measurements.filter((item) => item.outcome === 'stopped')
                      .length
                  }
                </strong>
              </div>
            </div>
            <h2 className="request-heading">Recent requests</h2>
            {measurements.length ? (
              <div className="request-table-wrap">
                <table className="request-table">
                  <thead>
                    <tr>
                      <th>Agent</th>
                      <th>Outcome</th>
                      <th>Elapsed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {measurements
                      .slice(-20)
                      .reverse()
                      .map((item) => (
                        <tr key={item.id}>
                          <td>{item.agent}</td>
                          <td>{item.outcome}</td>
                          <td>{(item.duration / 1000).toFixed(1)}s</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="metrics-empty">
                <Activity size={30} strokeWidth={1.2} />
                <h2>No live requests yet</h2>
                <span>Preview requests excluded</span>
              </div>
            )}
          </main>
        )}
      </div>
      {notice && (
        <div className="chat-toast" role="status">
          <Check size={16} />
          {notice}
          <button
            className="chat-icon"
            aria-label="Dismiss notification"
            onClick={() => setNotice('')}
          >
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  )
}
