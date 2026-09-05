import { useEffect, useState } from 'react'
import { LoaderCircle } from 'lucide-react'

export function WaitingIndicator({ label }: { label?: string }) {
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
      <LoaderCircle size={18} className="spin" />
      <span>Awaiting {label}</span>
      <span>{elapsed}s</span>
    </div>
  )
}
