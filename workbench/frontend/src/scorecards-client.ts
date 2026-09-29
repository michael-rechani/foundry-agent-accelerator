import { useEffect, useState } from 'react'
import { creationRequest } from './agent-creation-client'
import { parseScorecards, type Scorecards } from './scorecards'

export type ScorecardsState = {
  scorecards: Scorecards | null
  error: string
  retry: () => void
}

// Loads recorded test results once, when a library detail first shows them.
export function useScorecards(needed: boolean): ScorecardsState {
  const [scorecards, setScorecards] = useState<Scorecards | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!needed || scorecards || error) return
    const abort = new AbortController()
    void creationRequest('agent-scorecards', {}, abort.signal)
      .then((value) => {
        if (!abort.signal.aborted) setScorecards(parseScorecards(value))
      })
      .catch((problem) => {
        if (!abort.signal.aborted)
          setError(
            problem instanceof Error && problem.name !== 'AbortError'
              ? problem.message
              : 'The test results did not load.',
          )
      })
    return () => abort.abort()
  }, [needed, scorecards, error, attempt])
  return {
    scorecards,
    error,
    retry: () => {
      setError('')
      setAttempt((value) => value + 1)
    },
  }
}
