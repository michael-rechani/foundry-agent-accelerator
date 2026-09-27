import { useEffect, useState } from 'react'
import { creationRequest } from './agent-creation-client'
import { parseCatalog, type LibraryCatalog } from './library-catalog'

export type LibraryCatalogState = {
  catalog: LibraryCatalog | null
  error: string
  retry: () => void
}

// Loads the template catalog once, when first needed, for both the Library
// view and Chat's library previews.
export function useLibraryCatalog(needed: boolean): LibraryCatalogState {
  const [catalog, setCatalog] = useState<LibraryCatalog | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!needed || catalog || error) return
    const abort = new AbortController()
    void creationRequest('agent-templates', {}, abort.signal)
      .then((value) => {
        if (!abort.signal.aborted) setCatalog(parseCatalog(value))
      })
      .catch((problem) => {
        if (!abort.signal.aborted)
          setError(
            problem instanceof Error && problem.name !== 'AbortError'
              ? problem.message
              : 'The agent library did not load.',
          )
      })
    return () => abort.abort()
  }, [needed, catalog, error, attempt])
  return {
    catalog,
    error,
    retry: () => {
      setError('')
      setAttempt((value) => value + 1)
    },
  }
}
