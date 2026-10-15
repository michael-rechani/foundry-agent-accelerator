import type { RefObject } from 'react'
import { CircleAlert, RefreshCw, X } from 'lucide-react'
import { ChatWelcome, type DraftMode } from './ChatWelcome'
import type { Turn } from './conversation-types'
import { ConversationTurn } from './ConversationTurn'
import type { DemoScenario } from './demo-scenarios'
import { DemoRunGuide } from './ExploreDemos'
import { WaitingIndicator } from './WaitingIndicator'
import type { Agent, Config } from './workspace-config'

// The scrolling part of a chat: the guide for a demo, the welcome, the
// messages, the wait indicator and the error.
export function ChatMessages({
  config,
  agent,
  agentLabels,
  isPreview,
  inProgress,
  draftMode,
  presenting,
  busy,
  historyBusy,
  turns,
  pending,
  error,
  activeDemo,
  bottom,
  latestAnswer,
  onFreshDemo,
  onCloseDemo,
  onPrompt,
  onClearExample,
  onCreateAgent,
  onCopy,
  onDismissError,
  onRetry,
  agents,
  onChooseAgent,
  onAddOns,
}: {
  config: Config | null
  agent?: Agent
  agentLabels: Record<string, string>
  isPreview: boolean
  inProgress: boolean
  draftMode: DraftMode
  presenting: boolean
  busy: boolean
  historyBusy: boolean
  turns: Turn[]
  pending: string
  error: string
  activeDemo: DemoScenario | null
  bottom: RefObject<HTMLDivElement | null>
  latestAnswer: RefObject<HTMLElement | null>
  onFreshDemo: (scenario: DemoScenario) => void
  onCloseDemo: () => void
  onPrompt: (text: string) => void
  onClearExample: () => void
  onCreateAgent?: () => void
  onCopy: (text: string) => void
  onDismissError: () => void
  onRetry?: () => void
  agents: Agent[]
  onChooseAgent: (id: string) => void
  onAddOns: () => void
}) {
  return (
    <div className="conversation-scroll" aria-label="Conversation">
      {activeDemo && (
        <DemoRunGuide
          scenario={activeDemo}
          presenting={presenting}
          busy={busy || historyBusy}
          onFresh={() => onFreshDemo(activeDemo)}
          onClose={onCloseDemo}
        />
      )}
      {!turns.length && !pending ? (
        activeDemo ? null : (
          <ChatWelcome
            agent={agent}
            config={config}
            isPreview={isPreview}
            inProgress={inProgress}
            draftMode={draftMode}
            onPrompt={onPrompt}
            onClearExample={onClearExample}
            onCreateAgent={onCreateAgent}
            agents={agents}
            onChooseAgent={onChooseAgent}
            onAddOns={onAddOns}
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
              answerRef={index === turns.length - 1 ? latestAnswer : undefined}
              onCopy={onCopy}
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
          {onRetry && (
            <button
              type="button"
              className="chat-error-retry"
              onClick={onRetry}
            >
              <RefreshCw size={14} aria-hidden="true" /> Retry
            </button>
          )}
          <button
            className="chat-icon"
            aria-label="Dismiss error"
            onClick={onDismissError}
          >
            <X size={16} />
          </button>
        </div>
      )}
      <div ref={bottom} />
    </div>
  )
}
