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
        <span>Awaiting {label}</span>
        <span aria-hidden="true">{elapsed}s</span>
      </div>
      {expects && (
        <p className="chat-waiting-note">
          <strong>What you get</strong> {expects}
        </p>
      )}
      {elapsed >= slowAfterSeconds && (
        <p className="chat-waiting-note">
          Still working. Answers usually take a few seconds, but the first one
          after a quiet period can take about a minute.
        </p>
      )}
    </div>
  )
}
