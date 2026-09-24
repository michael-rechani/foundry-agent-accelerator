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
  specialist_receipts_checked: 'Records of specialist calls checked',
  citations_checked: 'Quotes matched to your documents',
  waiting_input: 'Additional information requested',
  completed: 'Results saved',
  failed: 'Review failed',
  interrupted: 'Execution interrupted',
}
const messages: Record<string, string> = {
  review_changed: 'This review changed. Refresh before continuing.',
  reviews_disabled: 'Review persistence is unavailable in this environment.',
  invalid_review: 'Check your documents, checklist and length limits.',
  review_not_runnable: 'This revision cannot be run again.',
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
  const data = await response.json()
  if (!response.ok)
    throw new Error(
      messages[data.error] ||
        'The request could not be confirmed. Refresh the inbox before repeating an action.',
    )
  return data
}
