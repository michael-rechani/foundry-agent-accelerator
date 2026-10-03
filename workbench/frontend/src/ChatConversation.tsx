import type { RefObject } from 'react'
import { ChatAside } from './ChatAside'
import { ChatComposer } from './ChatComposer'
import { ChatMessages } from './ChatMessages'
import type { chatLimits } from './chat-helpers'
import type { DemoScenario } from './demo-scenarios'
import type { Conversation } from './use-conversation'
import type { Agent, Config } from './workspace-config'

// The chat page: the conversation and its message box in the middle, and on
// wide screens the agent's details beside them.
export function ChatConversation({
  config,
  agent,
  conversation,
  historyBusy,
  isPreview,
  presenting,
  showAside,
  agentLabels,
  agentNotice,
  previewNotice,
  welcomeInProgress,
  limits,
  editor,
  bottom,
  latestAnswer,
  saveDisabled,
  saveNote,
  onFreshDemo,
  onCopy,
  onCreateAgent,
  onSubmit,
  onStop,
  onContinue,
  onCatalog,
  onSave,
  onExport,
  onCreateThis,
}: {
  config: Config | null
  agent?: Agent
  conversation: Conversation
  historyBusy: boolean
  isPreview: boolean
  presenting: boolean
  showAside: boolean
  agentLabels: Record<string, string>
  agentNotice: string
  previewNotice: string
  welcomeInProgress: boolean
  limits: ReturnType<typeof chatLimits>
  editor: RefObject<HTMLTextAreaElement | null>
  bottom: RefObject<HTMLDivElement | null>
  latestAnswer: RefObject<HTMLElement | null>
  saveDisabled: boolean
  saveNote?: string
  onFreshDemo: (scenario: DemoScenario) => void
  onCopy: (text: string) => void
  onCreateAgent?: () => void
  onSubmit: () => void
  onStop: () => void
  onContinue: () => void
  onCatalog: () => void
  onSave: () => void
  onExport: () => void
  onCreateThis?: () => void
}) {
  const {
    draft,
    turns,
    pending,
    busy,
    error,
    saved,
    dirty,
    activeDemo,
    setDraft,
    setPending,
    setError,
    setActiveDemo,
  } = conversation
  return (
    <div className="conversation-layout">
      <main className="conversation-view">
        {agentNotice && (
          <p className="creation-error" role="alert">
            {agentNotice}
          </p>
        )}
        {previewNotice && (
          <p className="creation-error" role="alert">
            {previewNotice}
          </p>
        )}
        <ChatMessages
          config={config}
          agent={agent}
          agentLabels={agentLabels}
          isPreview={isPreview}
          inProgress={welcomeInProgress}
          presenting={presenting}
          busy={busy}
          historyBusy={historyBusy}
          turns={turns}
          pending={pending}
          error={error}
          activeDemo={activeDemo}
          bottom={bottom}
          latestAnswer={latestAnswer}
          onFreshDemo={onFreshDemo}
          onCloseDemo={() => setActiveDemo(null)}
          onPrompt={(text) => {
            setDraft(text)
            setActiveDemo(null)
            editor.current?.focus()
          }}
          onCreateAgent={onCreateAgent}
          onCopy={onCopy}
          onDismissError={() => {
            setError('')
            setPending('')
          }}
        />
        <ChatComposer
          editor={editor}
          agent={agent}
          config={config}
          draft={draft}
          busy={busy}
          historyBusy={historyBusy}
          turnCount={turns.length}
          characters={limits.characters}
          requestBytes={limits.requestBytes}
          contextUsage={limits.contextUsage}
          limitReasons={limits.limitReasons}
          saved={!!saved}
          dirty={dirty}
          isPreview={isPreview}
          onDraft={(value) => {
            setDraft(value)
            if (!busy) setPending('')
          }}
          onSubmit={onSubmit}
          onStop={onStop}
          onContinue={onContinue}
        />
      </main>
      {showAside && agent && (
        <ChatAside
          agent={agent}
          config={config}
          isPreview={isPreview}
          turns={turns}
          characters={limits.characters}
          saving={historyBusy}
          saveDisabled={saveDisabled}
          saveNote={saveNote}
          exportDisabled={!turns.length && !draft}
          onCatalog={onCatalog}
          onSave={onSave}
          onExport={onExport}
          onCreateThis={onCreateThis}
        />
      )}
    </div>
  )
}
