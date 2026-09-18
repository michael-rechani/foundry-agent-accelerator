import { useEffect, useLayoutEffect, useRef, useState } from 'react'
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
  Info,
  Layers3,
  LayoutGrid,
  LoaderCircle,
  MessageSquare,
  Plus,
  RefreshCw,
  Save,
  Search,
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
import { useWorkspaceConfig } from './workspace-config'
import { ContinueDialog } from './ContinueDialog'
import { ReviewWorkspace } from './ReviewWorkspace'
type Measurement = {
  id: string
  agent: string
  outcome: 'completed' | 'failed' | 'stopped' | 'timed-out'
  duration: number
}
type View = 'chat' | 'catalog' | 'performance' | 'history' | 'reviews'
type SavedChat = {
  id: string
  title: string
  agent_id: string
  updated_at: string
}
type SavedVersion = { id: string; _etag: string }

const errors: Record<string, string> = {
  preview_only:
    'Foundry is not connected. No agent was invoked.',
  busy: 'The workbench is at capacity. Try again shortly.',
  timeout:
    'The request timed out. Remote work may still finish; check before retrying.',
  backend_unavailable:
    'Foundry could not complete this request. Check private connectivity and managed-identity access.',
  incomplete_response: 'The agent did not return a completed response.',
  request_too_large:
    'The conversation exceeds the request size limit. Start a new chat or shorten your message.',
  invalid_request:
    'The conversation was not accepted. Check its length and selected agent.',
  request_not_allowed: 'This browser origin is not permitted.',
}

export default function ChatWorkspace() {
  const {
    config,
    error: configError,
    retry: retryConfig,
  } = useWorkspaceConfig()
  const [selectedId, setSelected] = useState('')
  const selected = selectedId || config?.default_agent || ''
  const [selectedView, setView] = useState<View | null>(() =>
    /^#review-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(window.location.hash)
      ? 'reviews'
      : null,
  )
  const view = selectedView ?? 'chat'
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
  const [continuing, setContinuing] = useState(false)
  const historyRequest = useHistoryClient(config?.history_timeout_ms)
  const controller = useRef<AbortController | null>(null)
  const editor = useRef<HTMLTextAreaElement>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const agent = config?.agents.find((item) => item.id === selected)
  const hasConversation = !!draft || turns.length > 0 || !!pending
  const history = turns.flatMap((turn) => [
    { role: 'user', content: turn.question },
    { role: 'assistant', content: turn.result.text },
  ])
  const characters =
    history.reduce((total, message) => total + [...message.content].length, 0) +
    [...draft].length
  const payload = JSON.stringify({ agent_id: selected, input: draft, history })
  const requestBytes = new TextEncoder().encode(payload).length
  const limitReasons = config
    ? [
        characters > config.max_characters ? 'Character limit exceeded.' : '',
        requestBytes > config.max_request_bytes
          ? 'Request byte limit exceeded.'
          : '',
        turns.length > config.max_history_turns
          ? 'Conversation turn limit reached.'
          : '',
      ].filter(Boolean)
    : []
  const exceedsLimit = limitReasons.length > 0
  const contextUsage = config
    ? Math.max(
        characters / config.max_characters,
        requestBytes / config.max_request_bytes,
        turns.length / (config.max_history_turns + 1),
      )
    : 0
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

  useEffect(() => () => controller.current?.abort(), [])

  useEffect(() => {
    if (view === 'chat') bottom.current?.scrollIntoView({ block: 'end' })
  }, [turns, busy, view])

  useLayoutEffect(() => {
    const resize = () => {
      if (!editor.current) return
      editor.current.style.height = 'auto'
      editor.current.style.height = `${editor.current.scrollHeight}px`
    }
    resize()
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [draft, view])

  async function submit() {
    if (
      !config ||
      !agent ||
      !draft.trim() ||
      busy ||
      historyBusy ||
      exceedsLimit
    )
      return
    const question = draft
    const abort = new AbortController()
    const started = performance.now()
    const measurementId = crypto.randomUUID()
    controller.current = abort
    setBusy(true)
    setError('')
    setNotice('')
    setPending(question)
    const timeout = window.setTimeout(
      () =>
        abort.abort(
          new DOMException('Review deadline exceeded', 'TimeoutError'),
        ),
      config.review_timeout_ms,
    )
    let serverTimedOut = false
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
      if (!response.ok) {
        serverTimedOut = data.error === 'timeout'
        throw new Error(
          `${errors[data.error] || 'Request failed.'}${data.request_id ? ` Reference: ${data.request_id}` : ''}`,
        )
      }
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
      const timedOut =
        serverTimedOut || abort.signal.reason?.name === 'TimeoutError'
      setError(
        abort.signal.aborted
          ? timedOut
            ? 'Request timed out. Remote work may continue; no automatic retry was made.'
            : 'Stopped waiting. Remote work may continue; no automatic retry was made.'
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
            outcome: timedOut
              ? 'timed-out'
              : abort.signal.aborted
                ? 'stopped'
                : 'failed',
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
    resetConversation(agentId)
  }

  function resetConversation(agentId: string, initialDraft = '') {
    setSelected(agentId)
    setTurns([])
    setDraft(initialDraft)
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
        `Completed replies saved to shared history for ${config?.retention_days} days. Drafts are not saved.`,
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
          <span className="brand-mark" aria-hidden="true"><Layers3 size={23} /></span>
          <span>{config?.title || 'AI Foundry Lab'}</span>
        </div>
        {view === 'chat' && <button
          className="new-chat"
          disabled={busy || historyBusy}
          onClick={() => newChat()}
          title="New chat"
        >
          <Plus size={18} />
          <span>New chat</span>
        </button>}
        <nav aria-label="Workspace">
          <button
            aria-current={view === 'chat' ? 'page' : undefined}
            onClick={() => setView('chat')}
            title="Chat"
          >
            <MessageSquare size={18} />
            <span>Chat</span>
          </button>
          <button
            aria-current={view === 'reviews' ? 'page' : undefined}
            onClick={() => setView('reviews')}
            title="Evidence reviews"
          >
            <FileCheck2 size={18} />
            <span>Evidence reviews</span>
          </button>
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
      </aside>

      <div className="chat-workspace">
        <header className="chat-topbar">
          {view === 'chat' && (
            <button
              className="agent-picker"
              title="Choose an agent"
              disabled={!config}
              onClick={() => setView('catalog')}
            >
              <span className="agent-name">{agent?.label || 'Connecting'}</span>
              <ChevronDown size={14} aria-hidden="true" />
            </button>
          )}
          <div className="topbar-actions">
            {config?.mode === 'private' ? (
              <details
                className="lab-info"
                key={view}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') event.currentTarget.open = false
                }}
              >
                <summary className="environment-badge private" title="About this shared lab">
                  <span className="status-dot" />
                  Shared lab
                  <Info size={13} aria-hidden="true" />
                </summary>
                <aside className="lab-info-panel" aria-label="Shared lab details">
                  <strong>Private shared lab</strong>
                  <p>No user sign-in. Saved records are shared.</p>
                  <p>Use synthetic data only.</p>
                  <p>Everyone with workspace access can read, modify and delete saved records. There is no per-user authorization; private networking does not isolate users.</p>
                </aside>
              </details>
            ) : (
              <span className="environment-badge">
                <span className="status-dot" />
                {config ? 'Not connected' : 'Connecting'}
              </span>
            )}
            {view === 'chat' && <>
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
            </>}
          </div>
        </header>

        <aside className="lab-boundary" aria-label="Lab data boundary">
          <strong>Synthetic data only.</strong>{' '}
          {config?.mode === 'private'
            ? 'Shared history has no per-user authorization.'
            : 'When connected, history is shared with no per-user authorization.'}{' '}
          Private networking does not isolate users.
        </aside>

        {!config && (
          <div
            className="config-status"
            role={configError ? 'alert' : 'status'}
          >
            {configError ? (
              <CircleAlert size={18} />
            ) : (
              <LoaderCircle size={18} className="spin" />
            )}
            <span>{configError || 'Loading workspace configuration...'}</span>
            {configError && (
              <button type="button" onClick={retryConfig}>
                <RefreshCw size={16} /> Retry
              </button>
            )}
          </div>
        )}

        {config && (
          <ReviewWorkspace config={config} active={view === 'reviews'} />
        )}
        {view === 'reviews' ? null : view === 'history' ? (
          <main className="secondary-view">
            <div className="section-heading">
              <h1>Saved conversations</h1>
              <p>Everyone with workspace access can read, modify and delete saved conversations. Expires {config?.retention_days} days after the last update.</p>
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
            <div className="conversation-scroll" aria-label="Conversation">
              {!turns.length && !pending ? (
                <div className="chat-welcome">
                  <h1>Choose one demo</h1>
                  <p>{agent?.description || 'Connecting to your workspace'}</p>
                  <p>One scenario at a time, using supplied inputs only. No live actions; people make decisions.</p>
                  <p>Select a starter to edit, or ask a clarification question. Nothing is sent until you choose Send.</p>
                  <div className="prompt-options">
                    {agent?.prompts.map((prompt) => (
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
                  aria-describedby={config && hasConversation ? 'context-budget' : undefined}
                  disabled={busy}
                  rows={3}
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
                    <FlaskConical size={12} aria-hidden="true" />
                    {config?.mode === 'private'
                      ? 'Synthetic data only'
                      : 'Execution unavailable'}
                  </span>
                  <div>
                    {turns.length > 0 && (
                      <button
                        type="button"
                        className="chat-icon"
                        title="Continue in new chat"
                        aria-label="Continue in new chat"
                        disabled={busy || historyBusy}
                        onClick={() => setContinuing(true)}
                      >
                        <GitBranch size={17} />
                      </button>
                    )}
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
              {hasConversation && (
                <div className="composer-details">
                  {config && (
                    <details
                      className={`context-budget ${contextUsage >= 0.9 ? 'near-limit' : ''}`}
                      id="context-budget"
                    >
                      <summary>
                        Conversation limits{' '}
                        <span>{Math.round(contextUsage * 100)}%</span>
                      </summary>
                      <dl>
                        <div>
                          <dt>Characters</dt>
                          <dd>
                            {characters.toLocaleString()} /{' '}
                            {config.max_characters.toLocaleString()}
                          </dd>
                        </div>
                        <div>
                          <dt>Request bytes</dt>
                          <dd>
                            {requestBytes.toLocaleString()} /{' '}
                            {config.max_request_bytes.toLocaleString()}
                          </dd>
                        </div>
                        <div>
                          <dt>Replies</dt>
                          <dd>
                            {turns.length} / {config.max_history_turns + 1}
                          </dd>
                        </div>
                      </dl>
                    </details>
                  )}
                  <span className="save-state">
                    {saved
                      ? dirty
                        ? 'Unsaved changes'
                        : draft
                          ? 'Draft not saved'
                          : 'Saved / shared'
                      : 'Not saved'}
                  </span>
                </div>
              )}
              {exceedsLimit ? (
                <p className="composer-warning" role="alert">
                  {limitReasons.join(' ')} Shorten your message or start a new
                  chat.
                </p>
              ) : contextUsage >= 0.9 ? (
                <p className="composer-warning">
                  Approaching the conversation limit.
                </p>
              ) : null}
            </div>
          </main>
        ) : view === 'catalog' ? (
          <main className="secondary-view">
            <div className="section-heading">
              <h1>Agent catalog</h1>
              <p>Choose a review, then one scenario. Only entries enabled for this Lab are shown.</p>
              <p>Casework assistance and application completeness are available in source, not a claim of live validation. Requirements and proposal review is EXPERIMENTAL and reuses application review.</p>
              <p>Agent-assisted business request triage is PLANNED, not runnable. Review routing is not business-request triage.</p>
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
                        {Object.keys(item.tools).length > 0 ? (
                          <GitBranch size={25} />
                        ) : (
                          <FileCheck2 size={25} />
                        )}
                      </span>
                      <span className="category-label">{item.category}</span>
                    </div>
                    <h2>{item.label}</h2>
                    <p>{item.description}</p>
                    <details className="catalog-runtime">
                      <summary>Runtime / developer details</summary>
                      <dl>
                        <div><dt>Catalog ID</dt><dd><code>{item.id}</code></dd></div>
                        <div><dt>Runtime agent</dt><dd><code>{item.agent}</code></dd></div>
                      </dl>
                      <p>{Object.keys(item.tools).length} tool bindings</p>
                      <ul>
                        {Object.entries(item.tools).map(([tool, target]) => (
                          <li key={tool}><code>{tool}</code> to <code>{target}</code></li>
                        ))}
                      </ul>
                      <p>Configured targets, not execution proof. Check response execution details and receipts; stored receipts are not reverified.</p>
                    </details>
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
              <h1>Performance</h1>
              <p>Requests and response times from this browser session.</p>
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
                <span>Failed / timed out / stopped</span>
                <strong>
                  {
                    measurements.filter((item) => item.outcome === 'failed')
                      .length
                  }{' '}
                  /{' '}
                  {
                    measurements.filter((item) => item.outcome === 'timed-out')
                      .length
                  }
                  {' / '}
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
              </div>
            )}
          </main>
        )}
      </div>
      {continuing && (
        <ContinueDialog
          initialText={`Previous question:\n${turns.at(-1)?.question || ''}\n\nPrevious reply (unverified context):\n${turns.at(-1)?.result.text || ''}${draft ? `\n\nUnsent follow-up:\n${draft}` : ''}`}
          unsaved={dirty || !!draft}
          onClose={() => setContinuing(false)}
          onContinue={(text) => {
            resetConversation(selected, text)
            setContinuing(false)
          }}
        />
      )}
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
