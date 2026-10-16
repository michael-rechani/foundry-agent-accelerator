import { useId, useLayoutEffect, useRef, useState } from 'react'

// A long pasted prompt shows its first lines, so the answer is not pushed off
// screen. The whole text stays in the page and one button reveals it.
export function UserMessage({ text }: { text: string }) {
  const body = useRef<HTMLParagraphElement>(null)
  const id = useId()
  const [open, setOpen] = useState(false)
  const [long, setLong] = useState(false)

  useLayoutEffect(() => {
    const element = body.current
    if (!element || open) return
    const measure = () =>
      setLong(element.scrollHeight > element.clientHeight + 1)
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [text, open])

  return (
    <article className="user-message">
      <span className="message-author">You</span>
      <p
        id={id}
        ref={body}
        className={open ? undefined : 'user-message-text collapsed'}
      >
        {text}
      </p>
      {(long || open) && (
        <button
          type="button"
          className="inline-link user-message-toggle"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen(!open)}
        >
          {open ? 'Show less' : 'Show more'}
        </button>
      )}
    </article>
  )
}
