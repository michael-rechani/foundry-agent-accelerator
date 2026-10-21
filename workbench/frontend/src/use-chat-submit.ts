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
import { chatLimits, requestPayload } from './chat-helpers'
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
    turns,
    selected,
    thread,
    setBusy,
    setError,
    setPending,
    setTurns,
    setDirty,
    setDraft,
  } = conversation
  const controller = useRef<AbortController | null>(null)

  useEffect(() => () => controller.current?.abort(), [])

  function submit() {
    if (!draft.trim() || exceedsLimit) return
    return send(draft, payload, false)
  }

  // Sends a suggested next step without touching what the person is typing.
  function ask(text: string) {
    const { exceedsLimit: over, payload: body } = chatLimits({
      config,
      turns,
      draft: text,
      selected,
      thread,
    })
    if (over) return
    return send(text, body, false, true)
  }

  // Asks the last question again without it or the answer in the history. The
  // new answer replaces the old one, which stays under it for comparison.
  function retry() {
    const last = turns[turns.length - 1]
    if (!last) return
    const { payload: body } = requestPayload({
      turns: turns.slice(0, -1),
      input: last.question,
      selected,
      thread,
    })
    return send(last.question, body, true)
  }

  async function send(
    question: string,
    body: string,
    retrying: boolean,
    keepDraft = false,
  ) {
    if (!config || config.mode === 'preview' || !agent || busy || historyBusy)
      return
    const abort = new AbortController()
    const started = performance.now()
    const measurementId = crypto.randomUUID()
    controller.current = abort
    setBusy(true)
    void preloadMarkdown()
    setError(null)
    setNotice('')
    if (!retrying) {
      setPending(question)
      // The message moves into the transcript while it is sent; a failure puts
      // it back in the box so it can be edited or retried.
      if (!keepDraft) setDraft('')
    }
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
          body,
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
      const result = { ...data, ...('usage' in data ? { usage } : {}) }
      setTurns((previous) => {
        if (!retrying) return [...previous, { question, result }]
        const last = previous[previous.length - 1]
        if (!last) return previous
        return [
          ...previous.slice(0, -1),
          {
            question,
            result,
            earlier: [...(last.earlier ?? []), last.result],
          },
        ]
      })
      setDirty(true)
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
      if (!retrying && !keepDraft) setDraft((current) => current || question)
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

  return { submit, ask, retry, stop }
}
