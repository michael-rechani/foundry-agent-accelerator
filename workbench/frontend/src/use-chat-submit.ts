import { useEffect, useRef, type RefObject } from 'react'
import type { Conversation } from './use-conversation'
import { preloadMarkdown } from './markdown-loader'
import type { Measurement } from './performance-stats'
import {
  failureFromProblem,
  failureFromResponse,
  makeFailure,
  type ChatFailure,
} from './chat-failure'
import { requestJson } from './request'
import { parseUsage } from './token-usage'
import type { Agent, Config } from './workspace-config'

// Sends the draft to the agent and records the answer or the failure. Stopping
// waiting does not cancel remote work, and nothing is retried.
export function useChatSubmit({
  config,
  agent,
  conversation,
  historyBusy,
  exceedsLimit,
  payload,
  editor,
  setNotice,
  onMeasure,
}: {
  config: Config | null
  agent: Agent | undefined
  conversation: Conversation
  historyBusy: boolean
  exceedsLimit: boolean
  payload: string
  editor: RefObject<HTMLTextAreaElement | null>
  setNotice: (notice: string) => void
  onMeasure: (measurement: Measurement) => void
}) {
  const {
    draft,
    busy,
    setBusy,
    setError,
    setPending,
    setTurns,
    setDirty,
    setDraft,
  } = conversation
  const controller = useRef<AbortController | null>(null)

  useEffect(() => () => controller.current?.abort(), [])

  async function submit() {
    if (
      !config ||
      !agent ||
      !draft.trim() ||
      busy ||
      historyBusy ||
      exceedsLimit
    )
      return
    const question = draft
    const abort = new AbortController()
    const started = performance.now()
    const measurementId = crypto.randomUUID()
    controller.current = abort
    setBusy(true)
    void preloadMarkdown()
    setError(null)
    setNotice('')
    setPending(question)
    // The message moves into the transcript while it is sent; a failure puts it
    // back in the box so it can be edited or retried.
    setDraft('')
    const timeout = window.setTimeout(
      () =>
        abort.abort(
          new DOMException('Review deadline exceeded', 'TimeoutError'),
        ),
      config.review_timeout_ms,
    )
    let serverTimedOut = false
    let reference: string | undefined
    let failure: ChatFailure | undefined
    try {
      const { response, data } = await requestJson(
        '/api/reviews',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Workbench-Request': '1',
          },
          body: payload,
        },
        abort.signal,
      )
      if (typeof data.request_id === 'string') reference = data.request_id
      if (!response.ok) {
        serverTimedOut = data.error === 'timeout'
        failure = failureFromResponse(response, data)
        throw new Error(failure.message)
      }
      const usage = parseUsage(data.usage)
      setTurns((previous) => [
        ...previous,
        {
          question,
          result: { ...data, ...('usage' in data ? { usage } : {}) },
        },
      ])
      setDirty(true)
      setDraft('')
      setPending('')
      if (config?.mode === 'private')
        onMeasure({
          id: measurementId,
          agent: agent.label,
          agentId: agent.id,
          outcome: 'completed',
          duration: performance.now() - started,
          at: Date.now(),
          reference,
          usage,
        })
    } catch (problem) {
      const timedOut =
        serverTimedOut || abort.signal.reason?.name === 'TimeoutError'
      const message = abort.signal.aborted
        ? timedOut
          ? 'Request timed out. Remote work may continue; no automatic retry was made.'
          : 'Stopped waiting. Remote work may continue; no automatic retry was made.'
        : undefined
      const shown =
        failure ??
        (message ? makeFailure(message) : failureFromProblem(problem))
      setError(shown)
      setDraft((current) => current || question)
      setPending('')
      if (config?.mode === 'private')
        onMeasure({
          id: measurementId,
          agent: agent.label,
          agentId: agent.id,
          outcome: timedOut
            ? 'timed-out'
            : abort.signal.aborted
              ? 'stopped'
              : 'failed',
          duration: performance.now() - started,
          at: Date.now(),
          reference: reference ?? failure?.reference,
          message: shown.message,
        })
    } finally {
      window.clearTimeout(timeout)
      controller.current = null
      setBusy(false)
      editor.current?.focus()
    }
  }

  function stop() {
    controller.current?.abort()
  }

  return { submit, stop }
}
