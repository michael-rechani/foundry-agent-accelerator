import { useEffect, useState } from 'react'
import { LoaderCircle } from 'lucide-react'

const slowAfterSeconds = 20

export function WaitingIndicator({
  label,
  expects,
}: {
  label?: string
  expects?: string
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
