import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Check, CircleAlert, LoaderCircle, RefreshCw, X } from 'lucide-react'
import '@fontsource-variable/manrope'
import '@fontsource/ibm-plex-mono/400.css'
import './chat.css'
import { useHistoryClient } from './history-client'
import { ConversationTurn } from './ConversationTurn'
import type { Turn } from './conversation-types'
import { requestJson } from './request'
import { WaitingIndicator } from './WaitingIndicator'
import { useWorkspaceConfig, type Agent } from './workspace-config'
import { ContinueDialog } from './ContinueDialog'
import { ReviewWorkspace } from './ReviewWorkspace'
import { AgentCreationWorkspace } from './AgentCreationWorkspace'
import {
  creationRequest,
  parseCreatedAgent,
  useCreatedAgents,
} from './agent-creation-client'
import { ChatSidebar, type View } from './ChatSidebar'
import { ChatTopbar } from './ChatTopbar'
import { ChatWelcome } from './ChatWelcome'
import { ChatComposer } from './ChatComposer'
import { HistoryView, type SavedChat } from './HistoryView'
import { AgentCatalog } from './AgentCatalog'
import { PerformanceView, type Measurement } from './PerformanceView'
import { ExploreDemos, DemoRunGuide } from './ExploreDemos'
import { agentForDemo, type DemoScenario } from './demo-scenarios'
type SavedVersion = { id: string; _etag: string }

const errors: Record<string, string> = {
  preview_only: 'Foundry is not connected. No agent was invoked.',
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
    /^#review-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(
      window.location.hash,
    )
      ? 'reviews'
      : window.location.hash === '#chat'
        ? 'chat'
        : window.location.hash === '#create'
          ? 'create'
          : null,
  )
  const view =
    selectedView === 'create' && config && !config.agent_creation
      ? 'explore'
      : (selectedView ?? 'explore')
  const createdAgents = useCreatedAgents(config?.agent_creation)
  const availableAgents: Agent[] = [
    ...(config?.agents || []),
    ...createdAgents.records
      .map((record) => record.agent)
      .filter((item): item is Agent => item !== null),
  ]
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
  const [presenting, setPresenting] = useState(false)
  const [activeDemo, setActiveDemo] = useState<DemoScenario | null>(null)
  const historyRequest = useHistoryClient(config?.history_timeout_ms)
  const controller = useRef<AbortController | null>(null)
  const editor = useRef<HTMLTextAreaElement>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const agent = availableAgents.find((item) => item.id === selected)
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
    if (view !== 'chat') return
    if (activeDemo && !turns.length && !busy)
      bottom.current?.parentElement?.scrollTo({ top: 0 })
    else bottom.current?.scrollIntoView({ block: 'end' })
  }, [turns, busy, view, activeDemo])

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
    setActiveDemo(null)
  }

  function loadDemo(scenario: DemoScenario) {
    if (!config || busy || historyBusy) return
    const target = agentForDemo(
      scenario,
      availableAgents,
      createdAgents.records,
    )
    if (!target) {
      setNotice(
        'No matching agent is available. Your current messages are preserved.',
      )
      return
    }
    if (
      (draft || dirty) &&
      !window.confirm(
        'Load this fictional example in a fresh chat? Unsaved local messages will be cleared. Saved history is not deleted.',
      )
    )
      return
    resetConversation(target.id, scenario.input)
    setActiveDemo(scenario)
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
      if (
        !availableAgents.some((entry) => entry.id === data.agent_id) &&
        data.agent_id.startsWith('created-')
      ) {
        const record = parseCreatedAgent(
          await creationRequest(`agents/${data.agent_id}`),
        )
        if (!record.agent)
          throw new Error(
            'The saved conversation uses an agent that is no longer ready.',
          )
        createdAgents.update(record)
      }
      setSaved({ id: data.id, _etag: data._etag })
      setSelected(data.agent_id)
      setTurns(data.turns.map((turn: Turn) => ({ ...turn, stored: true })))
      setDirty(false)
      setDraft('')
      setPending('')
      setError('')
      setNotice('')
      setView('chat')
      setActiveDemo(null)
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
    <div
      className={`chat-app${config?.agent_creation ? ' has-creation' : ''}${presenting ? ' presenter-view' : ''}`}
    >
      <ChatSidebar
        title={config?.title}
        view={view}
        creationEnabled={!!config?.agent_creation}
        historyEnabled={!!config?.history_enabled}
        busy={busy}
        historyBusy={historyBusy}
        agentCount={availableAgents.length}
        onNewChat={() => newChat()}
        onView={setView}
        onCreatedAgents={() => {
          setView('created')
          void createdAgents.refresh()
        }}
        onHistory={() => void listHistory()}
      />

      <div className="chat-workspace">
        <ChatTopbar
          view={view}
          config={config}
          agent={agent}
          selected={selected}
          saving={historyBusy}
          saveDisabled={
            !config?.history_enabled ||
            !turns.length ||
            busy ||
            historyBusy ||
            !dirty
          }
          exportDisabled={!turns.length && !draft}
          presenting={presenting}
          onPresent={() => setPresenting((value) => !value)}
          onView={setView}
          onSave={() => void saveChat()}
          onExport={download}
        />

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
        {config?.agent_creation && (
          <AgentCreationWorkspace
            capability={config.agent_creation}
            state={createdAgents}
            active={view === 'create' || view === 'created'}
            view={view === 'create' ? 'create' : 'created'}
            chatBusy={busy || historyBusy}
            onView={setView}
            onUse={(item) => newChat(item.id)}
          />
        )}
        {view === 'explore' ? (
          config && (
            <ExploreDemos
              config={config}
              agents={availableAgents}
              created={createdAgents.records}
              loadingAgents={createdAgents.loading}
              agentError={createdAgents.error}
              busy={busy || historyBusy}
              onLoad={loadDemo}
              onCreate={(label) => {
                setView('create')
                if (label)
                  setNotice(
                    `Choose the ${label} template, then review its setup. Publication still requires operator approval.`,
                  )
              }}
              onChat={() => setView('chat')}
            />
          )
        ) : view === 'reviews' ||
          view === 'create' ||
          view === 'created' ? null : view === 'history' ? (
          <HistoryView
            chats={savedChats}
            agents={availableAgents}
            retentionDays={config?.retention_days}
            cursor={cursor}
            busy={busy}
            historyBusy={historyBusy}
            onOpen={(item) => void openChat(item)}
            onDelete={(item) => void deleteChat(item)}
            onMore={() => void listHistory(true)}
          />
        ) : view === 'chat' ? (
          <main className="conversation-view">
            {selected.startsWith('created-') &&
              !agent &&
              !createdAgents.loading && (
                <p className="creation-error" role="alert">
                  {createdAgents.error ||
                    'The selected created agent is unavailable or no longer ready. Choose another agent; your local messages are preserved.'}
                </p>
              )}
            <div className="conversation-scroll" aria-label="Conversation">
              {activeDemo && (
                <DemoRunGuide
                  scenario={activeDemo}
                  presenting={presenting}
                  busy={busy || historyBusy}
                  onFresh={() => loadDemo(activeDemo)}
                  onClose={() => setActiveDemo(null)}
                />
              )}
              {!turns.length && !pending ? (
                activeDemo ? null : (
                  <ChatWelcome
                    agent={agent}
                    config={config}
                    onPrompt={(text) => {
                      setDraft(text)
                      setActiveDemo(null)
                      editor.current?.focus()
                    }}
                    onReviews={() => setView('reviews')}
                  />
                )
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
            <ChatComposer
              editor={editor}
              agent={agent}
              config={config}
              draft={draft}
              busy={busy}
              historyBusy={historyBusy}
              turnCount={turns.length}
              hasConversation={hasConversation}
              characters={characters}
              requestBytes={requestBytes}
              contextUsage={contextUsage}
              limitReasons={limitReasons}
              saved={!!saved}
              dirty={dirty}
              onDraft={(value) => {
                setDraft(value)
                if (!busy) setPending('')
              }}
              onSubmit={() => void submit()}
              onStop={() => controller.current?.abort()}
              onContinue={() => setContinuing(true)}
            />
          </main>
        ) : view === 'catalog' ? (
          <AgentCatalog
            agents={availableAgents}
            selected={selected}
            query={query}
            loaded={!!config}
            creation={config?.agent_creation}
            disabled={busy || historyBusy}
            onQuery={setQuery}
            onCreate={() => setView('create')}
            onChoose={(id) => (id === selected ? setView('chat') : newChat(id))}
          />
        ) : (
          <PerformanceView measurements={measurements} />
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
