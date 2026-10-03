import { readJson } from './request.ts'

export type Source = { id: string; text: string }
export type Finding = {
  criterion_id: string
  assessment: 'supported' | 'gap' | 'conflict'
  explanation: string
  citations: { source_id: string; quote: string }[]
}
export type Run = {
  id: string
  started_at: string
  elapsed_ms?: number
  error?: string
  resumed_from?: string
  input: { criteria: string[]; evidence: Source[] }
  events: { name: string; at: string }[]
  result?: { summary: string; findings: Finding[]; questions: string[] }
  receipts?: {
    tool: string
    agent: string
    verified: boolean
    call_id: string
  }[]
}
export type Review = {
  id: string
  title: string
  agent_id: string
  status: string
  updated_at: string
  _etag: string
  criteria: string[]
  evidence: Source[]
  runs: Run[]
}
export type ReviewItem = Pick<Review, 'id' | 'title' | 'status' | 'updated_at'>

const reviewLink = /^#(review-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$/
export const reviewIdFromHash = (hash: string) =>
  reviewLink.exec(hash)?.[1] ?? null

export const statuses: Record<string, string> = {
  draft: 'Ready to run',
  running: 'Running',
  waiting_input: 'Needs information',
  completed: 'Results saved',
  failed: 'Failed',
  interrupted: 'Interrupted',
}
export const eventNames: Record<string, string> = {
  review_started: 'Review requested',
  review_recovery_requested: 'Recovery requested using saved input',
  specialist_receipts_checked: 'Records of specialist calls checked',
  citations_checked: 'Quotes matched to your documents',
  waiting_input: 'Additional information requested',
  completed: 'Results saved',
  failed: 'Review failed',
  interrupted: 'Execution interrupted',
}
const messages: Record<string, string> = {
  not_found:
    'That review could not be found. It may have been removed, or the link may be wrong.',
  request_timeout:
    'The upload took too long. Your draft is unchanged; check your connection before submitting again.',
  review_changed: 'This review changed. Refresh before continuing.',
  reviews_disabled: 'Review persistence is unavailable in this environment.',
  invalid_review: 'Check your documents, checklist and length limits.',
  review_not_runnable: 'This revision cannot be run again.',
  review_not_resumable:
    'This review cannot be recovered. Refresh to check whether it is still running or has reached its four-run limit.',
  recovery_confirmation_required:
    'Confirm that recovery starts a new call and may incur another model charge.',
  review_not_waiting: 'This review is not accepting more information.',
  busy: 'Agent capacity is busy. Try again later.',
  reviews_busy: 'Review requests are limited. Try again in a minute.',
}

export async function reviewRequest(
  path: string,
  method = 'GET',
  body?: unknown,
  etag?: string,
  signal?: AbortSignal,
) {
  const response = await fetch(`/api/review-runs${path}`, {
    method,
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(40000)])
      : AbortSignal.timeout(40000),
    headers: {
      'X-Workbench-Request': '1',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(etag ? { 'If-Match': etag } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  })
  const data = await readJson(response)
  if (!response.ok)
    throw new Error(
      messages[data.error] ||
        'The request could not be confirmed. Refresh the inbox before repeating an action.',
    )
  return data
}
