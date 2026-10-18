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
          <strong>Expect:</strong> {expects}
        </p>
      )}
      {delegates && (
        <p className="chat-waiting-note">
          <strong>Working:</strong> {label ?? 'This agent'} is passing your task
          to specialist agents and combining what they return. That usually
          takes 30 to 60 seconds.
        </p>
      )}
      {elapsed >= slowAfterSeconds && (
        <p className="chat-waiting-note">
          Still working. Some answers take 30 seconds to a minute, especially
          the first one in a new chat. Follow-up questions in the same chat
          usually take a few seconds.
        </p>
      )}
    </div>
  )
}
