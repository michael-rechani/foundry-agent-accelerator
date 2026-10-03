import { Check, X } from 'lucide-react'

export function ChatToast({
  notice,
  onDismiss,
}: {
  notice: string
  onDismiss: () => void
}) {
  return (
    <div className="chat-toast" role="status">
      <Check size={16} />
      {notice}
      <button
        className="chat-icon"
        aria-label="Dismiss notification"
        onClick={onDismiss}
      >
        <X size={15} />
      </button>
    </div>
  )
}
