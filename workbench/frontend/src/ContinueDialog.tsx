import { useEffect, useRef, useState } from 'react'
import { ArrowRight, X } from 'lucide-react'

export function ContinueDialog({
  initialText,
  unsaved,
  onClose,
  onContinue,
}: {
  initialText: string
  unsaved: boolean
  onClose: () => void
  onContinue: (text: string) => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [text, setText] = useState(initialText)
  useEffect(() => {
    const element = dialog.current!
    element.showModal()
    return () => element.close()
  }, [])
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
