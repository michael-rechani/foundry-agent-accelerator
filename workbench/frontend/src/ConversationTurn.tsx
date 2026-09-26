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
import type { Receipt, Turn } from './conversation-types'

type ReceiptState = 'verified' | 'unverified' | 'stored'

// Stored history is never reverified, so it can't claim live verification.
function receiptState(turn: Turn, receipt: Receipt): ReceiptState {
  if (turn.stored) return 'stored'
  return receipt.verified ? 'verified' : 'unverified'
}

const receiptLabels: Record<ReceiptState, string> = {
  verified: 'Verified receipt',
  unverified: 'Unverified call',
  stored: 'Stored / not reverified',
}

const stepLabels: Record<ReceiptState, string> = {
  verified: 'Verified',
  unverified: 'Unverified',
  stored: 'Stored - not reverified',
}

const stepIcons = {
  verified: CheckCheck,
  unverified: CircleAlert,
  stored: Archive,
}

function HandoffTimeline({
  turn,
  coordinator,
}: {
  turn: Turn
  coordinator: string
}) {
  return (
    <ol className="handoff-timeline" aria-label="Handoff timeline">
      <li>
        <MessageSquare size={13} aria-hidden="true" />
        <span>You asked</span>
      </li>
      <li>
        <ChevronRight className="handoff-arrow" size={12} aria-hidden="true" />
        <GitBranch size={13} aria-hidden="true" />
        <span>{coordinator}</span>
        <small>Coordinator</small>
      </li>
      {turn.result.receipts.map((receipt, index) => {
        const state = receiptState(turn, receipt)
        const Icon = stepIcons[state]
        return (
          <li
            className={`handoff-specialist ${state}`}
            key={`${receipt.call_id}-${index}`}
          >
            <ChevronRight
              className="handoff-arrow"
              size={12}
              aria-hidden="true"
            />
            <span>{receipt.agent || 'Target not verified'}</span>
            <small>
              <Icon size={12} aria-hidden="true" />
              {stepLabels[state]}
            </small>
          </li>
        )
      })}
      <li>
        <ChevronRight className="handoff-arrow" size={12} aria-hidden="true" />
        <UserCheck size={13} aria-hidden="true" />
        <span>You check the findings</span>
      </li>
    </ol>
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
  onCopy,
}: {
  turn: Turn
  label?: string
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
          <span>{(turn.result.elapsed_ms / 1000).toFixed(1)}s</span>
        </div>
        <Markdown text={turn.result.text} />
        {turn.result.receipts.length > 0 && (
          <HandoffTimeline
            turn={turn}
            coordinator={label || turn.result.agent}
          />
        )}
        <div className="response-tools">
          <button
            className="chat-icon"
            title="Copy response"
            aria-label="Copy response"
            onClick={() => onCopy(turn.result.text)}
          >
            <Clipboard size={15} />
          </button>
          <span>Human review required</span>
        </div>
        <details className="receipt-details">
          <summary>
            <Activity size={14} /> Execution details{' '}
            <span>{turn.result.receipts.length}</span>
          </summary>
          <code>{turn.result.request_id}</code>
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
