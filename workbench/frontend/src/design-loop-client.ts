// The browser side of "test this draft first". A model writes test cases for a
// draft's task instructions, then each case runs once per request against the
// draft without publishing anything. Results stay in the page and in a file the
// person downloads; the Lab stores none of it. Uses erasable TypeScript only so
// `node --test` can import it directly.

import { specSlug, type AgentSpec } from './agent-spec.ts'
import {
  failureFromProblem,
  failureFromResponse,
  failureMessages,
  makeFailure,
  type ChatFailure,
} from './chat-failure.ts'
import type { Receipt } from './conversation-types.ts'
import { requestJson } from './request.ts'
import { parseUsage, type Usage } from './token-usage.ts'

export type CaseChecks = {
  must_include?: string[]
  must_include_any?: string[][]
  guards?: string[]
  asks_question?: boolean
  expected_tools?: string[]
}

export type TestCase = {
  id: string
  category: string
  input: string
  checks: CaseChecks
  rubric: string
}

export type CaseRun = {
  request_id: string
  case_id: string
  passed: boolean
  failures: string[]
  text: string
  receipts: Receipt[]
  elapsed_ms: number
  usage: Usage | null
}

export type CaseDraft = {
  cases: TestCase[]
  // How many drafted cases the Lab dropped because they failed its checks.
  dropped: number
  usage: Usage | null
}

export type Job = { test: TestCase; repeat: number }

export const MAX_REPEATS = 3

const messages: Record<string, string> = {
  cases_unusable:
    'The model did not return usable test cases. Try again; nothing was published.',
  invalid_case:
    'That test case was not accepted, so it was not run. Write new cases.',
  invalid_setup:
    'The setup was not accepted. Check that the draft is not too long and that its template can be tested.',
  response_too_large:
    'The answer was too large to check, so this test was stopped.',
}

export class TestRequestError extends Error {
  readonly failure: ChatFailure

  constructor(failure: ChatFailure) {
    super(failure.message)
    this.failure = failure
  }
}

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

function describeFailure(response: Response, data: unknown) {
  const body = isObject(data) ? data : {}
  const failure = failureFromResponse(response, body)
  const code = typeof body.error === 'string' ? body.error : ''
  // The chat's busy message points at a retry countdown this panel does not
  // have, so a busy Lab gets the plain wait-and-continue wording here.
  const message =
    code === 'busy' ? failureMessages.busy : (messages[code] ?? failure.message)
  return message === failure.message
    ? failure
    : makeFailure(message, {
        reference: failure.reference,
        status: response.status,
      })
}

export function asFailure(problem: unknown) {
  return problem instanceof TestRequestError
    ? problem.failure
    : failureFromProblem(problem)
}

// One model call per request. A person stopping the work rethrows the abort so
// the caller can tell it from a timeout.
export async function designRequest(
  path: 'agent-test-cases' | 'agent-test-runs',
  body: unknown,
  timeoutMs: number,
  signal?: AbortSignal,
): Promise<unknown> {
  const combined = signal
    ? AbortSignal.any([signal, AbortSignal.timeout(timeoutMs)])
    : AbortSignal.timeout(timeoutMs)
  try {
    const { response, data } = await requestJson(
      '/api/' + path,
      {
        method: 'POST',
        headers: {
          'X-Workbench-Request': '1',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      },
      combined,
    )
    if (!response.ok)
      throw new TestRequestError(describeFailure(response, data))
    return data
  } catch (problem) {
    if (problem instanceof TestRequestError || signal?.aborted) throw problem
    if (
      problem instanceof DOMException &&
      (problem.name === 'AbortError' || problem.name === 'TimeoutError')
    )
      throw new TestRequestError(makeFailure(failureMessages.timeout))
    throw new TestRequestError(failureFromProblem(problem))
  }
}

const strings = (value: unknown, limit: number): string[] | null =>
  Array.isArray(value) &&
  value.length <= limit &&
  value.every((item) => typeof item === 'string')
    ? (value as string[])
    : null

function parseChecks(value: unknown): CaseChecks | null {
  if (!isObject(value)) return null
  const checks: CaseChecks = {}
  if (value.must_include !== undefined) {
    const list = strings(value.must_include, 6)
    if (!list) return null
    checks.must_include = list
  }
  if (value.must_include_any !== undefined) {
    const groups = Array.isArray(value.must_include_any)
      ? value.must_include_any.map((group) => strings(group, 6))
      : null
    if (!groups || groups.length > 3 || groups.some((group) => !group))
      return null
    checks.must_include_any = groups as string[][]
  }
  if (value.guards !== undefined) {
    const list = strings(value.guards, 6)
    if (!list) return null
    checks.guards = list
  }
  if (value.asks_question !== undefined) {
    if (typeof value.asks_question !== 'boolean') return null
    checks.asks_question = value.asks_question
  }
  if (value.expected_tools !== undefined) {
    const list = strings(value.expected_tools, 8)
    if (!list) return null
    checks.expected_tools = list
  }
  return checks
}

function parseCase(value: unknown): TestCase | null {
  if (
    !isObject(value) ||
    typeof value.id !== 'string' ||
    typeof value.category !== 'string' ||
    typeof value.input !== 'string' ||
    typeof value.rubric !== 'string'
  )
    return null
  const checks = parseChecks(value.checks)
  return checks
    ? {
        id: value.id,
        category: value.category,
        input: value.input,
        checks,
        rubric: value.rubric,
      }
    : null
}

export function parseCaseDraft(value: unknown): CaseDraft {
  if (!isObject(value) || !Array.isArray(value.cases))
    throw new Error('The test case response is invalid.')
  const cases = value.cases.map(parseCase)
  const ids = new Set(cases.map((item) => item?.id))
  if (!cases.length || cases.some((item) => !item) || ids.size !== cases.length)
    throw new Error('The test case response is invalid.')
  return {
    cases: cases as TestCase[],
    dropped: Array.isArray(value.rejected) ? value.rejected.length : 0,
    usage: parseUsage(value.usage),
  }
}

function parseReceipt(value: unknown): Receipt | null {
  const text = (field: unknown) =>
    field === null || typeof field === 'string'
      ? (field as string | null)
      : false
  if (
    !isObject(value) ||
    typeof value.tool !== 'string' ||
    typeof value.verified !== 'boolean' ||
    text(value.call_id) === false ||
    text(value.agent) === false ||
    text(value.output) === false
  )
    return null
  return {
    tool: value.tool,
    verified: value.verified,
    call_id: value.call_id as string | null,
    agent: value.agent as string | null,
    output: value.output as string | null,
  }
}

export function parseCaseRun(value: unknown): CaseRun {
  const failures = isObject(value) ? strings(value.failures, 50) : null
  const receipts =
    isObject(value) && Array.isArray(value.receipts)
      ? value.receipts.map(parseReceipt)
      : null
  if (
    !isObject(value) ||
    typeof value.request_id !== 'string' ||
    typeof value.case_id !== 'string' ||
    typeof value.passed !== 'boolean' ||
    typeof value.text !== 'string' ||
    typeof value.elapsed_ms !== 'number' ||
    !failures ||
    !receipts ||
    receipts.some((receipt) => !receipt)
  )
    throw new Error('The test result is invalid.')
  return {
    request_id: value.request_id,
    case_id: value.case_id,
    passed: value.passed,
    failures,
    text: value.text,
    receipts: receipts as Receipt[],
    elapsed_ms: value.elapsed_ms,
    usage: parseUsage(value.usage),
  }
}

// Every case once before any case twice, so an interrupted run still covers
// them all. A case that already has enough runs is skipped.
export function pendingJobs(
  cases: TestCase[],
  results: Record<string, CaseRun[]>,
  repeats: number,
): Job[] {
  const jobs: Job[] = []
  for (let repeat = 0; repeat < repeats; repeat++)
    for (const test of cases)
      if ((results[test.id]?.length ?? 0) <= repeat) jobs.push({ test, repeat })
  return jobs
}

export function describeChecks(checks: CaseChecks) {
  const quote = (items: string[]) => items.map((item) => `"${item}"`)
  const lines: string[] = []
  if (checks.must_include?.length)
    lines.push('Mentions ' + quote(checks.must_include).join(', '))
  for (const group of checks.must_include_any ?? [])
    lines.push('Mentions one of ' + quote(group).join(' or '))
  if (checks.guards?.length)
    lines.push(
      'Never ' +
        checks.guards.map((guard) => guard.replaceAll('_', ' ')).join(', '),
    )
  if (checks.asks_question) lines.push('Asks a question')
  if (checks.expected_tools?.length)
    lines.push('Calls ' + checks.expected_tools.join(', '))
  return lines
}

export function summarizeRuns(
  cases: TestCase[],
  results: Record<string, CaseRun[]>,
) {
  const runs = cases.flatMap((test) => results[test.id] ?? [])
  return {
    runs: runs.length,
    passed: runs.filter((run) => run.passed).length,
  }
}

export const testFileName = (spec: Pick<AgentSpec, 'name'>) =>
  `${specSlug(spec)}.test-cases.json`

// The cases and what came back, for a person to keep and to read against each
// rubric. The note travels with the file so a pass is never mistaken for proof.
export function testFile(input: {
  name: string
  templateId: string
  instructions: string
  cases: TestCase[]
  results: Record<string, CaseRun[]>
}) {
  return {
    note: 'The automatic checks only screen answers. A person must read each answer against its rubric before relying on this agent.',
    agent: input.name,
    template_id: input.templateId,
    instructions: input.instructions,
    cases: input.cases,
    runs: input.cases.flatMap((test) =>
      (input.results[test.id] ?? []).map((run) => ({
        case_id: run.case_id,
        passed: run.passed,
        failures: run.failures,
        answer: run.text,
        tools_called: run.receipts.map((receipt) => receipt.tool),
        elapsed_ms: run.elapsed_ms,
      })),
    ),
  }
}
