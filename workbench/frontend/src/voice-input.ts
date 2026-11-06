// Browser-independent parts of dictation. The browser's speech recognition
// isn't in TypeScript's DOM types, so the few members used here are described
// by hand. The Lab never receives audio; the browser sends it to its own speech
// service and hands back text.

export type SpeechResult = {
  readonly isFinal: boolean
  readonly length: number
  readonly [index: number]: { readonly transcript: string }
}

export type Recognizer = {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((event: { results: ArrayLike<SpeechResult> }) => void) | null
  onerror: ((event: { error: string }) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

export type RecognizerConstructor = new () => Recognizer

export type SpeechScope = {
  SpeechRecognition?: RecognizerConstructor
  webkitSpeechRecognition?: RecognizerConstructor
}

export const LISTENING_NOTICE =
  "Listening. Your browser's speech service turns audio into text and may send it to its provider. Select the microphone again to stop."

export const DICTATION_DISCLOSURE =
  "Dictation uses your browser's speech service, which may send audio to its provider. The Lab receives only the text you send."

export function recognizerConstructor(
  scope: SpeechScope,
): RecognizerConstructor | undefined {
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition
}

// A continuous session reports every result so far, so the whole transcript is
// rebuilt on each event rather than appended piece by piece.
export function transcriptOf(results: ArrayLike<SpeechResult>): string {
  const parts: string[] = []
  for (let index = 0; index < results.length; index++) {
    const text = results[index][0]?.transcript.trim()
    if (text) parts.push(text)
  }
  return parts.join(' ')
}

export function appendTranscript(base: string, transcript: string): string {
  const spoken = transcript.replace(/\s+/g, ' ').trim()
  if (!spoken) return base
  if (!base.trim()) return spoken
  return /\s$/.test(base) ? base + spoken : `${base} ${spoken}`
}

// Returns null for outcomes that need no message, such as the user stopping.
export function voiceErrorMessage(code: string): string | null {
  switch (code) {
    case 'aborted':
      return null
    case 'not-allowed':
    case 'service-not-allowed':
      return "Microphone access is blocked. Allow it in your browser's site settings, or type your message."
    case 'no-speech':
      return "I didn't hear anything. Select the microphone to try again."
    case 'audio-capture':
      return 'No microphone was found. Connect one, or type your message.'
    case 'network':
      return "Your browser's speech service couldn't be reached. Type your message, or try again."
    default:
      return 'Dictation stopped unexpectedly. Type your message, or select the microphone to try again.'
  }
}
