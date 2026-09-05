import { useEffect, useRef } from 'react'
import { requestJson } from './request'

const historyErrors: Record<string, string> = {
  conversation_changed:
    'This shared conversation changed in another browser. Reopen it before saving; export your local messages first.',
  conversation_too_large:
    'This conversation is too large to save (512 KiB limit). Export it instead.',
  conversation_not_found:
    'This shared conversation was deleted or expired. Your local messages are unchanged.',
}

export function useHistoryClient(timeoutMs: number | undefined) {
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => controller.current?.abort(), [])

  return async function historyRequest(
    path: string,
    options: RequestInit = {},
  ) {
    if (!timeoutMs) throw new Error('Workspace configuration is unavailable.')
    const abort = new AbortController()
    controller.current = abort
    const timeout = window.setTimeout(() => abort.abort(), timeoutMs)
    try {
      const headers = new Headers(options.headers)
      headers.set('X-Workbench-Request', '1')
      const { response, data } = await requestJson(
        `/api/conversations${path}`,
        {
          ...options,
          headers,
        },
        abort.signal,
      )
      if (!response.ok)
        throw new Error(
          historyErrors[data.error] ||
            'Saved history is unavailable. Your local messages are unchanged.',
        )
      return data
    } catch (problem) {
      if (abort.signal.aborted)
        throw new Error(
          'History request stopped after waiting. Your local messages are unchanged. A save may have completed; check shared history before retrying.',
        )
      throw problem
    } finally {
      window.clearTimeout(timeout)
      if (controller.current === abort) controller.current = null
    }
  }
}
