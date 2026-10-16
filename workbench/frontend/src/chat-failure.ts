// What a failed send tells the visitor: a plain sentence about what happened
// and what to do, with the technical reference kept apart from the sentence.
export type ChatFailure = {
  message: string
  reference?: string
  // Seconds the server asked the visitor to wait before trying again.
  retryAfter?: number
  // Plain text for "Copy details", for sharing with an operator.
  details: string
}

export const failureMessages: Record<string, string> = {
  preview_only: 'Foundry is not connected. No agent was invoked.',
  busy: 'The Lab is busy right now. Wait a minute, then try again.',
  timeout:
    'The request timed out. Remote work may still finish; check before retrying.',
  backend_unavailable:
    'Foundry could not complete this request. Check private connectivity and managed-identity access.',
  incomplete_response: 'The agent did not return a completed response.',
  request_too_large:
    'The conversation exceeds the request size limit. Start a new chat or shorten your message.',
  invalid_request:
    'The conversation was not accepted. Check its length and selected agent.',
  request_not_allowed: 'This browser origin is not permitted.',
  library_preview_disabled:
    'Library previews are turned off in this Lab. Choose a ready agent, or create this one from the Library.',
}

const busyWithCountdown =
  'The Lab is busy right now. Retry unlocks when the countdown ends.'
const gatewayMessage =
  'The Lab could not get a reply from its service. Wait a moment, then try again.'
const notReachedMessage =
  'Could not reach the Lab. Check your connection, then try again.'
const maxRetryAfterSeconds = 120

// Retry-After can also be a date; only the seconds form drives a countdown.
function parseRetryAfter(value: string | null) {
  if (!value || !/^\d+$/.test(value.trim())) return undefined
  const seconds = Number(value)
  return seconds > 0 ? Math.min(seconds, maxRetryAfterSeconds) : undefined
}

export function makeFailure(
  message: string,
  extra: { reference?: string; status?: number; retryAfter?: number } = {},
): ChatFailure {
  const lines = [message]
  if (extra.status) lines.push(`HTTP ${extra.status}`)
  if (extra.reference) lines.push(`Reference: ${extra.reference}`)
  lines.push(`Time: ${new Date().toISOString()}`)
  return {
    message,
    reference: extra.reference,
    retryAfter: extra.retryAfter,
    details: lines.join('\n'),
  }
}

// Turns an error response into a failure. The server's own request id wins over
// the Front Door reference, which is the only one when a request is blocked
// before it reaches the Lab.
export function failureFromResponse(
  response: Response,
  data: { error?: unknown; request_id?: unknown },
): ChatFailure {
  const code = typeof data.error === 'string' ? data.error : ''
  const status = response.status
  const reference =
    (typeof data.request_id === 'string' && data.request_id) ||
    response.headers.get('x-azure-ref') ||
    undefined
  const retryAfter =
    code === 'busy'
      ? parseRetryAfter(response.headers.get('Retry-After'))
      : undefined
  let message = failureMessages[code]
  if (!message)
    message =
      status >= 502 && status <= 504
        ? gatewayMessage
        : `Request failed (HTTP ${status}).`
  if (retryAfter) message = busyWithCountdown
  return makeFailure(message, { reference, status, retryAfter })
}

export function failureFromProblem(problem: unknown): ChatFailure {
  if (problem instanceof TypeError) return makeFailure(notReachedMessage)
  return makeFailure(
    problem instanceof Error ? problem.message : 'Request failed.',
  )
}
