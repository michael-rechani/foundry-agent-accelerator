import {
  Activity,
  CheckCheck,
  CircleAlert,
  Clipboard,
  GitBranch,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Turn } from './conversation-types'

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
                  {!turn.stored && receipt.verified ? (
                    <CheckCheck size={16} />
                  ) : (
                    <CircleAlert size={16} />
                  )}
                  <strong>{receipt.tool}</strong>
                  <span>
                    {turn.stored
                      ? 'Stored / not reverified'
                      : receipt.verified
                        ? 'Verified receipt'
                        : 'Unverified call'}
                  </span>
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
