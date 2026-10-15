import { useEffect, useState } from 'react'
import { CircleAlert, Copy, RefreshCw, X } from 'lucide-react'
import type { ChatFailure } from './chat-failure'

// The message that appears when a send fails: what happened, what to do, and
// the technical reference kept in its own small line.
export function ChatError({
  failure,
  onRetry,
  onDismiss,
  onCopy,
}: {
  failure: ChatFailure
  onRetry?: () => void
  onDismiss: () => void
  onCopy: (text: string, done?: string) => void
}) {
  const [deadline] = useState(
    () => Date.now() + (failure.retryAfter ?? 0) * 1000,
  )
  const [remaining, setRemaining] = useState(failure.retryAfter ?? 0)
  useEffect(() => {
    if (!failure.retryAfter) return
    const timer = window.setInterval(() => {
      const left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000))
      setRemaining(left)
      if (!left) window.clearInterval(timer)
    }, 500)
    return () => window.clearInterval(timer)
  }, [deadline, failure.retryAfter])
  return (
    <div className="chat-error" role="alert">
      <CircleAlert size={19} />
      <div className="chat-error-body">
        <p>{failure.message}</p>
        <p className="chat-error-reference">
          {failure.reference && <span>Reference: {failure.reference}</span>}
          <button
            type="button"
            className="chat-error-copy"
            onClick={() => onCopy(failure.details, 'Error details copied.')}
          >
            <Copy size={12} aria-hidden="true" /> Copy details
          </button>
        </p>
      </div>
      {onRetry && (
        <button
          type="button"
          className="chat-error-retry"
          aria-label="Retry"
          disabled={remaining > 0}
          onClick={onRetry}
        >
          <RefreshCw size={14} aria-hidden="true" /> Retry
          {remaining > 0 && <span aria-hidden="true"> in {remaining}s</span>}
        </button>
      )}
      <button
        className="chat-icon"
        aria-label="Dismiss error"
        onClick={onDismiss}
      >
        <X size={16} />
      </button>
    </div>
  )
}
