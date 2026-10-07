import { type RefObject, useRef, useState } from 'react'
import { ArrowRight, X } from 'lucide-react'
import { useModalDialog } from './use-modal-dialog'

export function ContinueDialog({
  initialText,
  unsaved,
  fallbackFocus,
  onClose,
  onContinue,
}: {
  initialText: string
  unsaved: boolean
  // Where focus lands once the button that opened this has gone, as it does
  // when the new chat starts.
  fallbackFocus?: RefObject<HTMLElement | null>
  onClose: () => void
  onContinue: (text: string) => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [text, setText] = useState(initialText)
  useModalDialog(dialog, fallbackFocus)
  return (
    <dialog
      ref={dialog}
      className="continue-dialog"
      aria-labelledby="continue-title"
      onCancel={(event) => {
        event.preventDefault()
        onClose()
      }}
    >
      <form
        onSubmit={(event) => {
          event.preventDefault()
          onContinue(text)
        }}
      >
        <header>
          <h2 id="continue-title">Continue in new chat</h2>
          <button
            type="button"
            className="chat-icon"
            aria-label="Close continuation"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </header>
        <label htmlFor="carry-over">Carry-over draft</label>
        <textarea
          id="carry-over"
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <p>
          {unsaved ? 'Unsaved source messages will be discarded. ' : ''}Saved
          history is unchanged. This draft has not been sent.
        </p>
        <footer>
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="primary-action">
            <ArrowRight size={16} /> Start new chat
          </button>
        </footer>
      </form>
    </dialog>
  )
}
