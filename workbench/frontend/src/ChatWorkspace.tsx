import { useState } from 'react'
import './chat.css'
import { useWorkspaceConfig, type Agent } from './workspace-config'
import { ConfirmDialog } from './ConfirmDialog'
import { ContinueDialog } from './ContinueDialog'
import { ReviewWorkspace } from './ReviewWorkspace'
import { AgentCreationWorkspace } from './AgentCreationWorkspace'
import { useCreatedAgents } from './agent-creation-client'
import { ChatSidebar, type View } from './ChatSidebar'
import { libraryViews } from './navigation'
import { LibraryTabs } from './LibraryTabs'
import { ChatTopbar } from './ChatTopbar'
import { ChatConfigStatus } from './ChatConfigStatus'
import { ChatConversation } from './ChatConversation'
import { ChatToast } from './ChatToast'
import { HistoryView, type SavedChat } from './HistoryView'
import { AgentCatalog } from './AgentCatalog'
import { PerformanceView } from './PerformanceView'
import type { Measurement } from './performance-stats'
import { RequestLog } from './RequestLog'
import { OperationsView } from './OperationsView'
import { AgentLibrary, type ReadyAgent } from './AgentLibrary'
import { ExploreDemos } from './ExploreDemos'
import { AddOns } from './AddOns'
import { isPreviewId, previewTemplateId } from './library-catalog'
import { agentForDemo, type DemoScenario } from './demo-scenarios'
import { hoodViews, loadUnderTheHood, saveUnderTheHood } from './under-the-hood'
import { chatLimits, exportConversation } from './chat-helpers'
import { useChatHistory } from './use-chat-history'
import { useChatSubmit } from './use-chat-submit'
import { useChatView } from './use-chat-view'
import {
  useAutoGrowEditor,
  useConversationScroll,
  useUnsavedWarning,
} from './use-chat-effects'
import { useConversation } from './use-conversation'
import { useDependencyHealth } from './use-dependency-health'
import { useLibraryPreviews } from './use-library-previews'

// A change that would clear the chat on screen, held until the person agrees.
type PendingChange = {
  title: string
  message: string
  confirmLabel: string
  run: () => void
}

export default function ChatWorkspace() {
  const {
    config,
    error: configError,
    retry: retryConfig,
  } = useWorkspaceConfig()
  const { view, setView } = useChatView(config)
  const conversation = useConversation(config?.default_agent)
  const { selected, draft, seed, turns, busy, dirty, activeDemo } = conversation
  const createdAgents = useCreatedAgents(config?.agent_creation)
  const availableAgents: Agent[] = [
    ...(config?.agents || []),
    ...createdAgents.records
      .map((record) => record.agent)
      .filter((item): item is Agent => item !== null),
  ]
  const {
    library,
    previewCapability,
    previewList,
    previewFor,
    previewsLoading,
    previewNote,
    previewOptions,
  } = useLibraryPreviews(config, view)
  const [notice, setNotice] = useState('')
  const [query, setQuery] = useState('')
  const [measurements, setMeasurements] = useState<Measurement[]>([])
  const [continuing, setContinuing] = useState(false)
  const [changing, setChanging] = useState<PendingChange | null>(null)
  const [presenting, setPresenting] = useState(false)
  const [hood, setHood] = useState(loadUnderTheHood)
  const [libraryDetail, setLibraryDetail] = useState('')
  const [requestedTemplate, setRequestedTemplate] = useState<{
    id: string
    key: number
  } | null>(null)
  const { dependencyHealth, loadDependencyHealth } = useDependencyHealth(view)
  const {
    historyBusy,
    savedChats,
    historyLoaded,
    cursor,
    listHistory,
    saveChat,
    openChat,
    deleteChat,
  } = useChatHistory({
    config,
    conversation,
    availableAgents,
    createdAgents,
    setView,
    setNotice,
  })
  const isPreview = isPreviewId(selected)
  const previewTemplate = previewTemplateId(selected)
  const agent = (isPreview ? previewList : availableAgents).find(
    (item) => item.id === selected,
  )
  const agentLabels = Object.fromEntries(
    availableAgents.map((item) => [item.agent, item.label]),
  )
  const readyOptions = availableAgents.map((item) => ({
    agent: item,
    detail: item.category,
  }))
  const limits = chatLimits({
    config,
    turns,
    draft,
    selected,
    thread: conversation.thread,
  })
  const unsaved = dirty || !!draft || busy
  const libraryCount = library.catalog?.templates.length
  const showAside =
    view === 'chat' && !!agent && turns.length > 0 && !presenting
  const saveDisabled =
    isPreview ||
    !config?.history_enabled ||
    !turns.length ||
    busy ||
    historyBusy ||
    !dirty
  const saveNote = isPreview ? "Preview chats can't be saved." : undefined
  const createThis =
    agent && previewTemplate && config?.agent_creation
      ? () => createFromTemplate(previewTemplate)
      : undefined

  useUnsavedWarning(unsaved)
  const { bottom, latestAnswer } = useConversationScroll(
    view,
    busy,
    turns,
    activeDemo,
  )
  const editor = useAutoGrowEditor(draft, view)
  const { submit, stop } = useChatSubmit({
    config,
    agent,
    conversation,
    historyBusy,
    exceedsLimit: limits.exceedsLimit,
    payload: limits.payload,
    editor,
    setNotice,
    onMeasure: (measurement) =>
      setMeasurements((previous) => [...previous, measurement]),
  })

  function agentLabel(id: string) {
    return [...availableAgents, ...previewList].find((item) => item.id === id)
      ?.label
  }

  // Asks before clearing messages the person wrote. An example the app put in
  // the message box, and left untouched, isn't theirs to lose.
  function confirmClear(
    title: string,
    confirmLabel: string,
    lead: string,
    run: () => void,
  ) {
    const draftEdited = draft.trim() !== '' && draft !== seed
    if (!dirty && !draftEdited) {
      run()
      return
    }
    const lost = !dirty
      ? 'draft'
      : draftEdited
        ? 'conversation and draft'
        : 'conversation'
    setChanging({
      title,
      confirmLabel,
      message:
        `${lead} Your unsaved ${lost} will be cleared. Saved history isn't deleted.`.trim(),
      run,
    })
  }

  function newChat(agentId = selected) {
    if (busy || historyBusy) return
    const start = () => resetConversation(agentId)
    if (agentId === selected)
      confirmClear('Start a new chat?', 'Start new chat', '', start)
    else
      confirmClear(
        `Switch to ${agentLabel(agentId) || 'this agent'}?`,
        'Switch agent',
        'Switching agents starts a new chat.',
        start,
      )
  }

  function resetConversation(agentId: string, initialDraft = '') {
    conversation.reset(agentId, initialDraft)
    setNotice('')
    setView('chat')
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
    confirmClear(
      'Open this example in a new chat?',
      'Open example',
      `The new chat uses ${target.label}.`,
      () => {
        resetConversation(target.id, scenario.input)
        conversation.setActiveDemo(scenario)
      },
    )
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
    confirmClear(
      'Open this example in a new chat?',
      'Open example',
      `The new chat uses ${target.label}.`,
      () => resetConversation(target.id, input),
    )
  }

  function openSaved(item: SavedChat) {
    if (busy || historyBusy) return
    confirmClear(
      'Open this conversation?',
      'Open conversation',
      '',
      () => void openChat(item),
    )
  }

  function createFromTemplate(templateId: string) {
    setRequestedTemplate((current) => ({
      id: templateId,
      key: (current?.key ?? 0) + 1,
    }))
    setView('create')
  }

  async function copy(text: string, done = 'Response copied.') {
    try {
      await navigator.clipboard.writeText(text)
      setNotice(done)
    } catch {
      setNotice('Clipboard unavailable. Select and copy the response manually.')
    }
  }

  return (
    <div
      className={`chat-app${config?.agent_creation ? ' has-creation' : ''}${presenting ? ' presenter-view' : ''}${hood ? ' under-the-hood' : ''}${showAside ? ' chat-has-aside' : ''}`}
    >
      <ChatSidebar
        title={config?.title}
        view={view}
        creationEnabled={!!config?.agent_creation}
        historyEnabled={!!config?.history_enabled}
        busy={busy}
        historyBusy={historyBusy}
        libraryCount={libraryCount}
        historyCount={historyLoaded ? savedChats.length : undefined}
        requestCount={measurements.length}
        hood={hood}
        foundryPortal={config?.foundry_portal}
        onNewChat={() => newChat()}
        onView={setView}
        onHistory={() => void listHistory()}
        onHood={(on) => {
          setHood(on)
          saveUnderTheHood(on)
          if (
            !on &&
            ((hoodViews as readonly View[]).includes(view) ||
              view === 'operations')
          )
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
          saveNote={saveNote}
          saveDisabled={saveDisabled}
          exportDisabled={!turns.length && !draft}
          presenting={presenting}
          onPresent={() => setPresenting((value) => !value)}
          onView={setView}
          onChoose={(id) => {
            if (id !== selected) newChat(id)
          }}
          onSave={() => void saveChat()}
          onExport={() => exportConversation(agent, turns, draft)}
          onCreateThis={createThis}
        />

        {!config && (
          <ChatConfigStatus error={configError} onRetry={retryConfig} />
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
            inLibrary={libraryViews.includes(view)}
            library={library}
            capability={config.agent_creation}
            readyAgentFor={readyAgentFor}
            previewFor={previewFor}
            foundryPortal={isPreview ? null : config?.foundry_portal}
            busy={busy || historyBusy}
            onOpen={setLibraryDetail}
            onCreate={createFromTemplate}
            onTest={testFromLibrary}
            onOpenCreate={
              config.agent_creation ? () => setView('create') : undefined
            }
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
        {view === 'addons' && <AddOns onNotice={setNotice} />}
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
          view === 'created' ? null : view === 'operations' ? (
          <OperationsView
            measurements={measurements}
            sampleCount={libraryCount}
            readyCount={availableAgents.length}
            createdCount={createdAgents.records.length}
            foundryPortal={config?.foundry_portal}
            health={dependencyHealth}
            onRefreshHealth={() => void loadDependencyHealth(true)}
            onLog={() => setView('log')}
          />
        ) : view === 'log' ? (
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
            onOpen={openSaved}
            onDelete={(item) => void deleteChat(item)}
            onMore={() => void listHistory(true)}
          />
        ) : view === 'chat' ? (
          <ChatConversation
            config={config}
            agent={agent}
            conversation={conversation}
            historyBusy={historyBusy}
            isPreview={isPreview}
            presenting={presenting}
            showAside={showAside}
            agentLabels={agentLabels}
            agentNotice={
              selected.startsWith('created-') &&
              !agent &&
              !createdAgents.loading
                ? createdAgents.error ||
                  'The selected created agent is unavailable or no longer ready. Choose another agent; your local messages are preserved.'
                : ''
            }
            previewNotice={
              isPreview &&
              !agent &&
              (library.error || !previewCapability?.enabled)
                ? previewNote ||
                  'This library preview is unavailable. Choose another agent.'
                : ''
            }
            welcomeInProgress={
              !!previewOptions.find((item) => item.agent.id === selected)
                ?.inProgress
            }
            limits={limits}
            editor={editor}
            bottom={bottom}
            latestAnswer={latestAnswer}
            saveDisabled={saveDisabled}
            saveNote={saveNote}
            onFreshDemo={loadDemo}
            onCopy={copy}
            onCreateAgent={
              !isPreview && config?.agent_creation
                ? () => setView('create')
                : undefined
            }
            onSubmit={() => void submit()}
            onStop={stop}
            onContinue={() => setContinuing(true)}
            onCatalog={() => setView('catalog')}
            onSave={() => void saveChat()}
            onExport={() => exportConversation(agent, turns, draft)}
            onCreateThis={createThis}
            agents={availableAgents}
            onChooseAgent={newChat}
            onAddOns={() => setView('addons')}
          />
        ) : view === 'catalog' ? (
          <AgentCatalog
            agents={availableAgents}
            selected={selected}
            query={query}
            loaded={!!config}
            creation={config?.agent_creation}
            previewsOn={!!config?.library_preview?.enabled}
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
      {changing && (
        <ConfirmDialog
          title={changing.title}
          message={changing.message}
          confirmLabel={changing.confirmLabel}
          onCancel={() => setChanging(null)}
          onConfirm={() => {
            changing.run()
            setChanging(null)
          }}
        />
      )}
      {continuing && (
        <ContinueDialog
          initialText={`Previous question:\n${turns.at(-1)?.question || ''}\n\nPrevious reply (unverified context):\n${turns.at(-1)?.result.text || ''}${draft ? `\n\nUnsent follow-up:\n${draft}` : ''}`}
          unsaved={dirty || !!draft}
          fallbackFocus={editor}
          onClose={() => setContinuing(false)}
          onContinue={(text) => {
            resetConversation(selected, text)
            setContinuing(false)
          }}
        />
      )}
      {notice && <ChatToast notice={notice} onDismiss={() => setNotice('')} />}
    </div>
  )
}
