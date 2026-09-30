import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Check, CircleAlert, LoaderCircle, RefreshCw, X } from 'lucide-react'
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
import { libraryViews } from './navigation'
import { LibraryTabs } from './LibraryTabs'
import { ChatTopbar } from './ChatTopbar'
import { ChatWelcome } from './ChatWelcome'
import { ChatComposer } from './ChatComposer'
import { HistoryView, type SavedChat } from './HistoryView'
import { AgentCatalog } from './AgentCatalog'
import { PerformanceView } from './PerformanceView'
import type { Measurement } from './performance-stats'
import { RequestLog } from './RequestLog'
import { AgentLibrary, type ReadyAgent } from './AgentLibrary'
import { ExploreDemos, DemoRunGuide } from './ExploreDemos'
import { AddOns } from './AddOns'
import { useLibraryCatalog } from './library-catalog-client'
import { isPreviewId, previewAgents } from './library-catalog'
import { agentForDemo, type DemoScenario } from './demo-scenarios'
import { parseUsage } from './token-usage'
import { hoodViews, loadUnderTheHood, saveUnderTheHood } from './under-the-hood'
type SavedVersion = { id: string; _etag: string }

// Identifies one conversation so the server can reuse its warm agent session.
const newThread = () =>
  typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : undefined

const hashViews: Record<string, View> = {
  '#chat': 'chat',
  '#create': 'create',
  '#library': 'library',
  '#agents': 'catalog',
  '#demos': 'explore',
  '#addons': 'addons',
  '#reviews': 'reviews',
  '#performance': 'performance',
  '#logs': 'log',
}

const errors: Record<string, string> = {
  preview_only: 'Foundry is not connected. No agent was invoked.',
  busy: 'The Lab is busy right now. Wait a minute, then try again.',
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
  library_preview_disabled:
    'Library previews are turned off in this Lab. Choose a ready agent, or create this one from the Library.',
}

const previewReasons: Record<string, string> = {
  local_preview: 'Library previews need a connected Lab.',
  not_enabled: 'Library previews are turned off in this Lab.',
  model_not_configured:
    'Library previews need a model deployment. Ask the Lab operator.',
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
      : (hashViews[window.location.hash] ?? null),
  )
  useEffect(() => {
    const follow = () => {
      const next = hashViews[window.location.hash]
      if (next) setView(next)
    }
    window.addEventListener('hashchange', follow)
    return () => window.removeEventListener('hashchange', follow)
  }, [])
  const view =
    selectedView === 'create' && config && !config.agent_creation
      ? 'library'
      : (selectedView ?? 'library')
  const createdAgents = useCreatedAgents(config?.agent_creation)
  const availableAgents: Agent[] = [
    ...(config?.agents || []),
    ...createdAgents.records
      .map((record) => record.agent)
      .filter((item): item is Agent => item !== null),
  ]
  const previewCapability = config?.library_preview
  const library = useLibraryCatalog(
    !!config && (view === 'library' || !!previewCapability?.enabled),
  )
  const previewList = previewCapability?.enabled
    ? previewAgents(library.catalog, previewCapability.agent)
    : []
  const previewFor = (templateId: string) =>
    previewList.find((item) => item.id === `library-${templateId}`)
  const previewsLoading =
    !!previewCapability?.enabled && !library.catalog && !library.error
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
  const [hood, setHood] = useState(loadUnderTheHood)
  const [libraryDetail, setLibraryDetail] = useState('')
  const [activeDemo, setActiveDemo] = useState<DemoScenario | null>(null)
  const [requestedTemplate, setRequestedTemplate] = useState<{
    id: string
    key: number
  } | null>(null)
  const [thread, setThread] = useState(newThread)
  const historyRequest = useHistoryClient(config?.history_timeout_ms)
  const controller = useRef<AbortController | null>(null)
  const editor = useRef<HTMLTextAreaElement>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const isPreview = isPreviewId(selected)
  const agent = (isPreview ? previewList : availableAgents).find(
    (item) => item.id === selected,
  )
  const agentLabels = Object.fromEntries(
    availableAgents.map((item) => [item.agent, item.label]),
  )
  const previewNote = !previewCapability
    ? ''
    : !previewCapability.enabled
      ? previewReasons[previewCapability.reason || ''] ||
        'Library previews are unavailable.'
      : library.error
        ? 'The library did not load. Open the Library to retry.'
        : !library.catalog
          ? 'Loading library previews...'
          : ''
  const readyOptions = availableAgents.map((item) => ({
    agent: item,
    detail: item.category,
  }))
  const previewOptions = previewList.map((item) => {
    const template = library.catalog?.templates.find(
      (entry) => `library-${entry.id}` === item.id,
    )
    return {
      agent: item,
      detail: template
        ? `Preview · ${template.sector.label} · ${template.industry.label}`
        : 'Preview',
      inProgress: template?.readiness.id === 'sample',
    }
  })
  const history = turns.flatMap((turn) => [
    { role: 'user', content: turn.question },
    { role: 'assistant', content: turn.result.text },
  ])
  const characters =
    history.reduce((total, message) => total + [...message.content].length, 0) +
    [...draft].length
  const payload = JSON.stringify({
    agent_id: selected,
    input: draft,
    history,
    thread,
  })
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
    let reference: string | undefined
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
      if (typeof data.request_id === 'string') reference = data.request_id
      if (!response.ok) {
        serverTimedOut = data.error === 'timeout'
        throw new Error(
          `${errors[data.error] || 'Request failed.'}${data.request_id ? ` Reference: ${data.request_id}` : ''}`,
        )
      }
      const usage = parseUsage(data.usage)
      setTurns((previous) => [
        ...previous,
        {
          question,
          result: { ...data, ...('usage' in data ? { usage } : {}) },
        },
      ])
      setDirty(true)
      setDraft('')
      setPending('')
      if (config?.mode === 'private')
        setMeasurements((previous) => [
          ...previous,
          {
            id: measurementId,
            agent: agent.label,
            agentId: agent.id,
            outcome: 'completed',
            duration: performance.now() - started,
            at: Date.now(),
            reference,
            usage,
          },
        ])
    } catch (problem) {
      const timedOut =
        serverTimedOut || abort.signal.reason?.name === 'TimeoutError'
      const message = abort.signal.aborted
        ? timedOut
          ? 'Request timed out. Remote work may continue; no automatic retry was made.'
          : 'Stopped waiting. Remote work may continue; no automatic retry was made.'
        : problem instanceof Error
          ? problem.message
          : 'Request failed.'
      setError(message)
      if (config?.mode === 'private')
        setMeasurements((previous) => [
          ...previous,
          {
            id: measurementId,
            agent: agent.label,
            agentId: agent.id,
            outcome: timedOut
              ? 'timed-out'
              : abort.signal.aborted
                ? 'stopped'
                : 'failed',
            duration: performance.now() - started,
            at: Date.now(),
            reference,
            message,
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
    setThread(newThread())
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
      previewFor,
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
        'Load this example in a fresh chat? Unsaved local messages will be cleared. Saved history is not deleted.',
      )
    )
      return
    resetConversation(target.id, scenario.input)
    setActiveDemo(scenario)
  }

  function readyAgentFor(templateId: string): ReadyAgent | undefined {
    const record = createdAgents.records.find(
      (item) =>
        item.template_id === templateId &&
        item.status === 'ready' &&
        item.agent !== null,
    )
    return record?.agent
      ? { agent: record.agent, recordId: record.id }
      : undefined
  }

  function testFromLibrary(target: Agent, input: string) {
    if (busy || historyBusy) return
    if (
      (draft || dirty) &&
      !window.confirm(
        'Open this example in a fresh chat? Unsaved local messages will be cleared. Saved history is not deleted.',
      )
    )
      return
    resetConversation(target.id, input)
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
      setThread(newThread())
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

  async function copy(text: string, done = 'Response copied.') {
    try {
      await navigator.clipboard.writeText(text)
      setNotice(done)
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
      className={`chat-app${config?.agent_creation ? ' has-creation' : ''}${presenting ? ' presenter-view' : ''}${hood ? ' under-the-hood' : ''}`}
    >
      <ChatSidebar
        title={config?.title}
        view={view}
        creationEnabled={!!config?.agent_creation}
        historyEnabled={!!config?.history_enabled}
        busy={busy}
        historyBusy={historyBusy}
        requestCount={measurements.length}
        hood={hood}
        foundryPortal={config?.foundry_portal}
        onNewChat={() => newChat()}
        onView={setView}
        onHistory={() => void listHistory()}
        onHood={(on) => {
          setHood(on)
          saveUnderTheHood(on)
          if (!on && (hoodViews as readonly View[]).includes(view))
            setView('library')
        }}
      />

      <div className="chat-workspace">
        <ChatTopbar
          view={view}
          detail={view === 'library' ? libraryDetail : ''}
          config={config}
          agent={agent}
          selected={selected}
          readyOptions={readyOptions}
          previewOptions={previewOptions}
          previewNote={previewNote}
          switchDisabled={busy || historyBusy}
          isPreview={isPreview}
          saving={historyBusy}
          saveNote={
            isPreview
              ? "Preview chats can't be saved. Create this agent from the Library to save conversations."
              : undefined
          }
          saveDisabled={
            isPreview ||
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
          onChoose={(id) => {
            if (id !== selected) newChat(id)
          }}
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

        {config && libraryViews.includes(view) && (
          <LibraryTabs
            view={view}
            readyCount={availableAgents.length}
            createdCount={createdAgents.records.length}
            creationEnabled={!!config.agent_creation}
            onView={setView}
            onCreated={() => {
              setView('created')
              void createdAgents.refresh()
            }}
          />
        )}
        {config && (
          <ReviewWorkspace config={config} active={view === 'reviews'} />
        )}
        {config && (
          <AgentLibrary
            active={view === 'library'}
            library={library}
            capability={config.agent_creation}
            readyAgentFor={readyAgentFor}
            previewFor={previewFor}
            foundryPortal={isPreview ? null : config?.foundry_portal}
            busy={busy || historyBusy}
            onOpen={setLibraryDetail}
            onCreate={(id) => {
              setRequestedTemplate((current) => ({
                id,
                key: (current?.key ?? 0) + 1,
              }))
              setView('create')
            }}
            onTest={testFromLibrary}
          />
        )}
        {config?.agent_creation && (
          <AgentCreationWorkspace
            capability={config.agent_creation}
            state={createdAgents}
            active={view === 'create' || view === 'created'}
            view={view === 'create' ? 'create' : 'created'}
            requestedTemplate={requestedTemplate}
            chatBusy={busy || historyBusy}
            onView={setView}
            onUse={(item) => newChat(item.id)}
          />
        )}
        {view === 'addons' && <AddOns />}
        {view === 'explore' ? (
          config && (
            <ExploreDemos
              config={config}
              agents={availableAgents}
              created={createdAgents.records}
              previewFor={previewFor}
              loadingAgents={createdAgents.loading || previewsLoading}
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
          view === 'addons' ||
          view === 'library' ||
          view === 'create' ||
          view === 'created' ? null : view === 'log' ? (
          <RequestLog
            measurements={measurements}
            preview={config?.mode !== 'private'}
            foundryPortal={config?.foundry_portal}
            onCopy={(text) => void copy(text, 'Reference copied.')}
          />
        ) : view === 'history' ? (
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
            {isPreview &&
              !agent &&
              (library.error || !previewCapability?.enabled) && (
                <p className="creation-error" role="alert">
                  {previewNote ||
                    'This library preview is unavailable. Choose another agent.'}
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
                    isPreview={isPreview}
                    inProgress={
                      !!previewOptions.find(
                        (item) => item.agent.id === selected,
                      )?.inProgress
                    }
                    onPrompt={(text) => {
                      setDraft(text)
                      setActiveDemo(null)
                      editor.current?.focus()
                    }}
                  />
                )
              ) : (
                <div className="message-list">
                  {turns.map((turn, index) => (
                    <ConversationTurn
                      key={`${turn.result.request_id}-${index}`}
                      turn={turn}
                      label={agent?.label}
                      agentLabels={agentLabels}
                      foundryPortal={isPreview ? null : config?.foundry_portal}
                      agentName={agent?.agent}
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
              {busy && (
                <WaitingIndicator
                  label={agent?.label}
                  expects={agent?.guidance?.output}
                />
              )}
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
              characters={characters}
              requestBytes={requestBytes}
              contextUsage={contextUsage}
              limitReasons={limitReasons}
              saved={!!saved}
              dirty={dirty}
              isPreview={isPreview}
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
            foundryPortal={config?.foundry_portal}
            disabled={busy || historyBusy}
            onQuery={setQuery}
            onCreate={() => setView('create')}
            onChoose={(id) => (id === selected ? setView('chat') : newChat(id))}
          />
        ) : (
          <PerformanceView
            measurements={measurements}
            preview={config?.mode !== 'private'}
            budgetAlerts={config?.budget_alerts === true}
            foundryPortal={config?.foundry_portal}
            onLog={() => setView('log')}
          />
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
