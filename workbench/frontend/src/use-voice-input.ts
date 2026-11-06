import { useCallback, useEffect, useRef, useState } from 'react'
import {
  LISTENING_NOTICE,
  type Recognizer,
  type SpeechScope,
  appendTranscript,
  recognizerConstructor,
  transcriptOf,
  voiceErrorMessage,
} from './voice-input'

const Recognition = recognizerConstructor(
  (typeof window === 'undefined' ? {} : window) as SpeechScope,
)

// Dictation fills the draft the user already has. It never sends anything: the
// transcript is editable text until the user presses Send. Any change to the
// draft that dictation didn't make (typing, sending, an example prompt) ends
// the session and drops what it hadn't written yet.
export function useVoiceInput(draft: string, onDraft: (value: string) => void) {
  const [listening, setListening] = useState(false)
  const [error, setError] = useState('')
  const recognizer = useRef<Recognizer | null>(null)
  const base = useRef('')
  const written = useRef('')
  const write = useRef(onDraft)

  useEffect(() => {
    write.current = onDraft
  })

  const cancel = useCallback(() => {
    const active = recognizer.current
    if (!active) return
    recognizer.current = null
    active.onresult = active.onerror = active.onend = null
    active.abort()
    setListening(false)
  }, [])

  useEffect(() => {
    if (recognizer.current && draft !== written.current) cancel()
  }, [draft, cancel])

  useEffect(() => cancel, [cancel])

  const toggle = useCallback(() => {
    if (!Recognition) return
    if (recognizer.current) {
      recognizer.current.stop()
      return
    }
    const next = new Recognition()
    next.lang = document.documentElement.lang || navigator.language || 'en-US'
    next.continuous = true
    next.interimResults = true
    base.current = draft
    written.current = draft
    next.onresult = (event) => {
      const value = appendTranscript(base.current, transcriptOf(event.results))
      written.current = value
      write.current(value)
    }
    next.onerror = (event) => setError(voiceErrorMessage(event.error) ?? '')
    next.onend = () => {
      if (recognizer.current === next) recognizer.current = null
      setListening(false)
    }
    recognizer.current = next
    setError('')
    try {
      next.start()
      setListening(true)
    } catch {
      recognizer.current = null
      setError(voiceErrorMessage('unknown') ?? '')
    }
  }, [draft])

  return {
    supported: !!Recognition,
    listening,
    toggle,
    status: listening ? LISTENING_NOTICE : error,
  }
}
