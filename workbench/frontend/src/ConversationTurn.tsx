import {
  Activity,
  Archive,
  CheckCheck,
  ChevronRight,
  CircleAlert,
  Clipboard,
  GitBranch,
  MessageSquare,
  UserCheck,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  plainStep,
  receiptState,
  stepsSummary,
  type ReceiptState,
} from './answer-steps'
import type { Turn } from './conversation-types'
import { usageDetail, usageLabel } from './token-usage'

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
}: {
  turn: Turn
  agentLabels?: Record<string, string>
}) {
  const usage = usageLabel(turn.result.usage)
  return (
    <details className="answer-steps">
      <summary>
        <ChevronRight
          className="answer-steps-chevron"
          size={14}
          aria-hidden="true"
        />
        <strong>How I got this</strong>
        <span>{stepsSummary(turn)}</span>
      </summary>
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
              {usage && ` ? ${usage}`}
            </small>
          </span>
        </li>
      </ol>
      {turn.result.receipts.length === 0 && (
        <p className="answer-steps-note">
          No lookups or other agents were recorded for this answer.
        </p>
      )}
    </details>
  )
}

function Markdown({ text }: { text: string }) {
  return (
    <div className="message-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ children }) => <span className="source-link">{children}</span>,
          img: ({ alt }) => <span>{alt}</span>,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}

export function ConversationTurn({
  turn,
  label,
  agentLabels,
  onCopy,
}: {
  turn: Turn
  label?: string
  agentLabels?: Record<string, string>
  onCopy: (text: string) => void
}) {
  return (
    <div className="turn">
      <article className="user-message">
        <span className="message-author">You</span>
        <p>{turn.question}</p>
      </article>
      <article className="assistant-message">
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
        <AnswerSteps turn={turn} agentLabels={agentLabels} />
        <div className="response-tools">
          <button
            className="chat-icon"
            title="Copy response"
            aria-label="Copy response"
            onClick={() => onCopy(turn.result.text)}
          >
            <Clipboard size={15} />
          </button>
          <span className="review-note">
            <UserCheck size={14} aria-hidden="true" /> Check this answer before
            you use it. A person makes the final decision.
          </span>
        </div>
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
      </article>
    </div>
  )
}
