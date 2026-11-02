import { useEffect, useState } from 'react'
import { LoaderCircle } from 'lucide-react'

const slowAfterSeconds = 20

export function WaitingIndicator({
  label,
  expects,
  delegates,
}: {
  label?: string
  expects?: string
  // True when the agent hands the work to specialist agents, which takes longer.
  delegates?: boolean
}) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const started = Date.now()
    const timer = window.setInterval(
      () => setElapsed(Math.floor((Date.now() - started) / 1000)),
      1000,
    )
    return () => window.clearInterval(timer)
  }, [])
  return (
    <div className="chat-waiting" role="status">
      <div className="chat-waiting-row">
        <LoaderCircle size={18} className="spin" />
        <span>Asking {label ?? 'the agent'}…</span>
        <span aria-hidden="true">{elapsed}s</span>
      </div>
      {expects && (
        <p className="chat-waiting-note">
          <strong>You'll get:</strong> {expects}
        </p>
      )}
      {delegates && (
        <p className="chat-waiting-note">
          <strong>What's happening:</strong> {label ?? 'This agent'} reads your
          request, hands it to a specialist agent that does the detailed check,
          then returns that answer to you. That usually takes 30 to 60 seconds.
        </p>
      )}
      {elapsed >= slowAfterSeconds && (
        <p className="chat-waiting-note">
          Still working. The first answer in a new chat is the slowest.
          Follow-up questions usually take a few seconds.
        </p>
      )}
    </div>
  )
}
