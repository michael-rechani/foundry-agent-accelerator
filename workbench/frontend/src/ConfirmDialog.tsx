import { useRef } from 'react'
import { useModalDialog } from './use-modal-dialog'

// A small in-app confirmation that names what is about to happen. Cancel takes
// the initial focus so a stray Enter never discards a conversation.
export function ConfirmDialog({
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  title: string
  message: string
  confirmLabel: string
  onConfirm: () => void
  onCancel: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  useModalDialog(dialog)
  return (
    <dialog
      ref={dialog}
      className="continue-dialog confirm-dialog"
      aria-labelledby="confirm-title"
      aria-describedby="confirm-message"
      onCancel={(event) => {
        event.preventDefault()
        onCancel()
      }}
    >
      <header>
        <h2 id="confirm-title">{title}</h2>
      </header>
      <p id="confirm-message">{message}</p>
      <footer>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="primary-action" onClick={onConfirm}>
          {confirmLabel}
        </button>
      </footer>
    </dialog>
  )
}
