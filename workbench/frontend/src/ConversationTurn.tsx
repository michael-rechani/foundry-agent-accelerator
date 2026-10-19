import {
  Activity,
  Archive,
  CheckCheck,
  ChevronRight,
  CircleAlert,
  Clipboard,
  GitBranch,
  MessageSquare,
  RotateCcw,
  UserCheck,
} from 'lucide-react'
import { useEffect, useState, type RefObject } from 'react'
import {
  plainStep,
  receiptState,
  stepsSummary,
  type ReceiptState,
} from './answer-steps'
import { AnswerFeedback } from './AnswerFeedback'
import type { Rating, Result, Turn } from './conversation-types'
import { FoundryLink } from './FoundryLink'
import { foundryAgentUrl } from './foundry-links'
import { loadedMarkdown, preloadMarkdown } from './markdown-loader'
import { usageDetail, usageLabel } from './token-usage'
import { UserMessage } from './UserMessage'

const receiptLabels: Record<ReceiptState, string> = {
  verified: 'Verified receipt',
  unverified: 'Unverified call',
  stored: 'Stored / not reverified',
}

const stepLabels: Record<ReceiptState, string> = {
  verified: 'Confirmed',
  unverified: 'Not confirmed',
  stored: 'Saved earlier',
}

const stepHints: Record<ReceiptState, string> = {
  verified: 'The Lab confirmed this step ran.',
  unverified: 'The Lab could not confirm this step ran.',
  stored: 'Saved with the conversation; not checked again.',
}

const stepIcons = {
  verified: CheckCheck,
  unverified: CircleAlert,
  stored: Archive,
}

function AnswerSteps({
  turn,
  agentLabels,
  foundryPortal,
  agentName,
}: {
  turn: Turn
  agentLabels?: Record<string, string>
  foundryPortal?: string | null
  agentName?: string
}) {
  const usage = usageLabel(turn.result.usage)
  const agentUrl = foundryAgentUrl(foundryPortal, agentName)
  return (
    <section className="answer-steps">
      <h4>How I got this</h4>
      <ol aria-label="How I got this">
        {turn.result.receipts.map((receipt, index) => {
          const state = receiptState(turn, receipt)
          const Icon = stepIcons[state]
          return (
            <li
              className={`answer-step ${state}`}
              key={`${receipt.call_id}-${index}`}
            >
              <span className="answer-step-dot" aria-hidden="true">
                <Icon size={12} />
              </span>
              <span className="answer-step-text">
                {plainStep(turn, receipt, agentLabels)}
                <small className="hood-only">
                  <code>{receipt.tool}</code>
                  {receipt.agent && (
                    <>
                      {' \u2192 '}
                      <code>{receipt.agent}</code>
                      {foundryPortal && (
                        <>
                          {' '}
                          <FoundryLink
                            href={foundryAgentUrl(foundryPortal, receipt.agent)}
                          >
                            Open in Foundry
                          </FoundryLink>
                        </>
                      )}
                    </>
                  )}
                </small>
              </span>
              <small className="answer-step-state" title={stepHints[state]}>
                {stepLabels[state]}
              </small>
            </li>
          )
        })}
        <li className="answer-step answer">
          <span className="answer-step-dot" aria-hidden="true">
            <MessageSquare size={12} />
          </span>
          <span className="answer-step-text">
            Wrote the answer
            <small className="hood-only">
              {(turn.result.elapsed_ms / 1000).toFixed(1)} s total
              {usage && ` \u00b7 ${usage}`}
            </small>
          </span>
          <small
            className="answer-step-result"
            title="The reply below was written after these steps."
          >
            Done
          </small>
        </li>
      </ol>
      {turn.result.receipts.some(
        (receipt) => receiptState(turn, receipt) !== 'stored',
      ) && (
        <p className="answer-steps-note">
          Confirmed means the Lab has a record that the step ran. It does not
          mean the content is correct.
        </p>
      )}
      {turn.result.receipts.length === 0 && (
        <p className="answer-steps-note">
          No lookups or other agents were recorded for this answer.
        </p>
      )}
      {agentUrl && (
        <p className="answer-steps-note hood-only">
          <FoundryLink href={agentUrl}>
            See this agent&apos;s traces in Foundry
          </FoundryLink>
        </p>
      )}
    </section>
  )
}

function detailsSummary(turn: Turn) {
  const earlier = turn.earlier?.length ?? 0
  const steps = stepsSummary(turn)
  if (!earlier) return steps
  return `${steps} \u00b7 ${earlier} earlier ${earlier === 1 ? 'answer' : 'answers'}`
}

function Markdown({ text }: { text: string }) {
  const [Formatter, setFormatter] = useState(loadedMarkdown)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    if (Formatter) return
    let current = true
    void preloadMarkdown().then((found) => {
      if (!current) return
      if (found) setFormatter(() => found)
      else setFailed(true)
    })
    return () => {
      current = false
    }
  }, [Formatter])
  return (
    <div className="message-markdown">
      {Formatter ? (
        <Formatter text={text} />
      ) : failed ? (
        <pre>{text}</pre>
      ) : null}
    </div>
  )
}

function EarlierAnswers({ answers }: { answers: Result[] }) {
  return (
    <details className="earlier-answers">
      <summary>
        <ChevronRight
          className="answer-steps-chevron"
          size={14}
          aria-hidden="true"
        />
        <strong>
          {answers.length === 1
            ? 'Earlier answer'
            : `${answers.length} earlier answers`}
        </strong>
        <span>Kept so you can compare. Not saved to shared history.</span>
      </summary>
      {answers.map((answer, index) => (
        <section
          className="earlier-answer"
          key={`${answer.request_id}-${index}`}
          aria-label={`Earlier answer ${index + 1}`}
        >
          <h4>
            Answer {index + 1} · {(answer.elapsed_ms / 1000).toFixed(1)}s
            {usageLabel(answer.usage) && (
              <span className="hood-only"> · {usageLabel(answer.usage)}</span>
            )}
          </h4>
          <Markdown text={answer.text} />
        </section>
      ))}
    </details>
  )
}

export function ConversationTurn({
  turn,
  label,
  agentLabels,
  foundryPortal,
  agentName,
  answerRef,
  latest = false,
  showReviewNote = true,
  plain = false,
  busy = false,
  onCopy,
  onRate,
  onTryAgain,
}: {
  turn: Turn
  label?: string
  agentLabels?: Record<string, string>
  foundryPortal?: string | null
  agentName?: string
  answerRef?: RefObject<HTMLElement | null>
  latest?: boolean
  showReviewNote?: boolean
  // A plain conversation has no steps, receipts or answer to check.
  plain?: boolean
  busy?: boolean
  onCopy: (text: string) => void
  onRate: (rating: Rating | undefined) => void
  onTryAgain?: () => void
}) {
  return (
    <div className="turn">
      <UserMessage text={turn.question} />
      <article ref={answerRef} className="assistant-message">
        <div className="assistant-heading">
          <span className="agent-avatar">
            <GitBranch size={16} />
          </span>
          <strong>{label}</strong>
          <span>
            {(turn.result.elapsed_ms / 1000).toFixed(1)}s
            {usageLabel(turn.result.usage) && (
              <span className="hood-only">
                {' '}
                · {usageLabel(turn.result.usage)}
              </span>
            )}
          </span>
        </div>
        <Markdown text={turn.result.text} />
        <div className={`response-tools${latest ? ' latest' : ''}`}>
          <button
            className="chat-icon"
            title="Copy response"
            aria-label="Copy response"
            onClick={() => onCopy(turn.result.text)}
          >
            <Clipboard size={15} />
          </button>
          {onTryAgain && (
            <button
              type="button"
              className="try-again"
              title="Ask the same question again. The earlier answer stays below for comparison."
              disabled={busy}
              onClick={onTryAgain}
            >
              <RotateCcw size={14} aria-hidden="true" /> Try again
            </button>
          )}
          <AnswerFeedback rating={turn.rating} onRate={onRate} />
        </div>
        {!plain && (
          <details className="answer-details">
            <summary>
              <ChevronRight
                className="answer-steps-chevron"
                size={14}
                aria-hidden="true"
              />
              <strong>Details</strong>
              <span>{detailsSummary(turn)}</span>
            </summary>
            <AnswerSteps
              turn={turn}
              agentLabels={agentLabels}
              foundryPortal={foundryPortal}
              agentName={agentName}
            />
            {turn.earlier?.length ? (
              <EarlierAnswers answers={turn.earlier} />
            ) : null}
            <details className="receipt-details hood-only">
              <summary>
                <Activity size={14} aria-hidden="true" /> Execution details
                <span>
                  {turn.result.receipts.length === 0
                    ? 'No tool calls'
                    : `${turn.result.receipts.length} tool ${turn.result.receipts.length === 1 ? 'call' : 'calls'}`}
                </span>
              </summary>
              <code>{turn.result.request_id}</code>
              {turn.result.usage !== undefined && (
                <p className="usage-detail">
                  {turn.result.usage
                    ? `Tokens: ${usageDetail(turn.result.usage)}.`
                    : 'The service did not report token usage for this answer.'}{' '}
                  Counts come from the answering agent&apos;s response. A
                  coordinator&apos;s count may not include specialists it calls.
                </p>
              )}
              {turn.result.receipts.length ? (
                turn.result.receipts.map((receipt, index) => (
                  <div className="receipt" key={`${receipt.call_id}-${index}`}>
                    <div>
                      {receiptState(turn, receipt) === 'verified' ? (
                        <CheckCheck size={16} />
                      ) : (
                        <CircleAlert size={16} />
                      )}
                      <strong>{receipt.tool}</strong>
                      <span>{receiptLabels[receiptState(turn, receipt)]}</span>
                    </div>
                    <code>{receipt.agent || 'Target not verified'}</code>
                    {receipt.output && (
                      <details>
                        <summary>What it returned</summary>
                        <Markdown text={receipt.output} />
                      </details>
                    )}
                  </div>
                ))
              ) : (
                <p>No tool calls were recorded for this answer.</p>
              )}
            </details>
          </details>
        )}
        {latest && showReviewNote && (
          <p className="review-note" role="note">
            <UserCheck size={14} aria-hidden="true" /> Check this answer before
            you use it. A person makes the final decision.
          </p>
        )}
      </article>
    </div>
  )
}
