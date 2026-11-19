import { useEffect, useRef, useState } from 'react'
import { asFailure, designRequest } from './design-loop-client'

export function PromptAgentTry({
  instructions,
  timeoutMs,
  disabled,
  active,
  onRunning,
}: {
  instructions: string
  timeoutMs: number
  disabled: boolean
  active?: boolean
  onRunning: (running: boolean) => void
}) {
  const [sample, setSample] = useState('')
  const [consent, setConsent] = useState(false)
  const [answer, setAnswer] = useState('')
  const [error, setError] = useState('')
  const [running, setRunning] = useState(false)
  const request = useRef<AbortController | null>(null)

  useEffect(() => () => request.current?.abort(), [])
  useEffect(() => {
    if (active === false) request.current?.abort()
  }, [active])

  async function tryPrompt() {
    if (request.current || disabled || !sample.trim() || !consent) return
    const attempt = new AbortController()
    request.current = attempt
    onRunning(true)
    setRunning(true)
    setConsent(false)
    setAnswer('')
    setError('')
    try {
      const result = await designRequest(
        'prompt-agent-tries',
        { instructions, prompt: sample, confirm_cost: true },
        timeoutMs,
        attempt.signal,
      )
      if (
        !result ||
        typeof result !== 'object' ||
        !('text' in result) ||
        typeof result.text !== 'string' ||
        !result.text.trim()
      )
        throw new Error('The model did not return a usable response.')
      if (!attempt.signal.aborted) setAnswer(result.text)
    } catch (problem) {
      setError(
        attempt.signal.aborted
          ? 'Stopped waiting. A model call already sent may still incur charges.'
          : asFailure(problem).message,
      )
    } finally {
      request.current = null
      setRunning(false)
      onRunning(false)
    }
  }

  return (
    <details className="spec-prompt-try">
      <summary>Try these instructions (optional)</summary>
      <p>
        One paid model call. No tools or sources are available, and no agent is
        created.
      </p>
      <label className="spec-prompt-field">
        Sample message
        <textarea
          rows={3}
          maxLength={2000}
          value={sample}
          disabled={running}
          onChange={(event) => {
            setSample(event.target.value)
            setConsent(false)
            setAnswer('')
            setError('')
          }}
        />
      </label>
      <label className="creation-consent">
        <input
          type="checkbox"
          checked={consent}
          disabled={running}
          onChange={(event) => setConsent(event.target.checked)}
        />
        <span>I confirm this try can incur model charges.</span>
      </label>
      <div className="agent-spec-actions">
        <button
          type="button"
          className="library-secondary"
          disabled={disabled || running || !sample.trim() || !consent}
          onClick={() => void tryPrompt()}
        >
          {running ? 'Waiting for the model…' : 'Run one try'}
        </button>
      </div>
      {error && (
        <p role="alert" className="spec-build-error">
          {error}
        </p>
      )}
      {answer && (
        <div role="status" className="spec-prompt-answer">
          <strong>Draft response</strong>
          <p>{answer}</p>
        </div>
      )}
    </details>
  )
}
