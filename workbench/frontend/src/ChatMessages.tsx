import type { RefObject } from 'react'
import type { ChatFailure } from './chat-failure'
import { ChatError } from './ChatError'
import { ChatWelcome, type DraftMode } from './ChatWelcome'
import { UserMessage } from './UserMessage'
import type { Rating, Turn } from './conversation-types'
import { ConversationTurn } from './ConversationTurn'
import type { DemoScenario } from './demo-scenarios'
import { DemoRunGuide } from './ExploreDemos'
import { isHelpQuestion } from './help-prompt'
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
  onDemoStep,
  onPrompt,
  onCopy,
  onRate,
  onDismissError,
  onRetry,
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
  error: ChatFailure | null
  activeDemo: DemoScenario | null
  bottom: RefObject<HTMLDivElement | null>
  latestAnswer: RefObject<HTMLElement | null>
  onFreshDemo: (scenario: DemoScenario) => void
  onCloseDemo: () => void
  onDemoStep: (prompt: string) => void
  onPrompt: (text: string) => void
  onCopy: (text: string, done?: string) => void
  onRate: (index: number, rating: Rating | undefined) => void
  onDismissError: () => void
  onRetry?: () => void
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
          onLoadStep={onDemoStep}
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
              showReviewNote={!isHelpQuestion(turn.question, agent?.prompts)}
              onCopy={onCopy}
              onRate={(rating) => onRate(index, rating)}
            />
          ))}
          {pending && <UserMessage text={pending} />}
        </div>
      )}
      {busy && (
        <WaitingIndicator
          label={agent?.label}
          expects={agent?.guidance?.output}
          delegates={!!agent && Object.keys(agent.tools).length > 0}
        />
      )}
      {error && (
        <ChatError
          key={error.details}
          failure={error}
          onRetry={onRetry}
          onDismiss={onDismissError}
          onCopy={onCopy}
        />
      )}
      <div ref={bottom} />
    </div>
  )
}
