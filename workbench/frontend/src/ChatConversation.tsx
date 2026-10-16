import type { RefObject } from 'react'
import { ChatAside } from './ChatAside'
import { ChatComposer } from './ChatComposer'
import { ChatMessages } from './ChatMessages'
import { saveStateText, type chatLimits } from './chat-helpers'
import type { DemoScenario } from './demo-scenarios'
import type { Conversation } from './use-conversation'
import type { Agent, Config } from './workspace-config'

// The chat page: the conversation and its message box in the middle, and on
// wide screens the agent's details beside them from the first screen on, so the
// layout does not shift after the first reply.
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
  onCopy: (text: string, done?: string) => void
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
    seed,
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
    prefill,
  } = conversation
  const draftMode = !draft.trim()
    ? 'empty'
    : draft === seed
      ? 'example'
      : 'typed'
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
          draftMode={draftMode}
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
            prefill(text)
            setActiveDemo(null)
            editor.current?.focus()
          }}
          onCopy={onCopy}
          onRetry={
            agent &&
            draft.trim() &&
            !busy &&
            !historyBusy &&
            !limits.limitReasons.length
              ? onSubmit
              : undefined
          }
          onDismissError={() => {
            setError(null)
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
          onCopyPrompt={() => onCopy(draft, 'Prompt copied.')}
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
          saveState={
            turns.length
              ? saveStateText({ isPreview, saved: !!saved, dirty, draft })
              : 'Nothing to save yet'
          }
          onCatalog={onCatalog}
          onSave={onSave}
          onExport={onExport}
          onCreateThis={onCreateThis}
        />
      )}
    </div>
  )
}
