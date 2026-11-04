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

export type Revision = {
  instructions: string
  changes: string[]
  usage: Usage | null
}

export type DiffLine = { kind: 'same' | 'add' | 'remove'; text: string }

export const MAX_REPEATS = 3
// A fixed budget of tries: after this many accepted revisions the next change is the person's.
export const MAX_REVISIONS = 2
// How many cases that passed are run again after a revision, to catch a change that broke them.
export const PASS_SAMPLE = 2
// The most failed cases one revision call reads, and the most of each answer sent with it.
export const MAX_FAILED = 5
export const MAX_ANSWER = 3000

const messages: Record<string, string> = {
  cases_unusable:
    'The model did not return usable test cases. Try again; nothing was published.',
  invalid_case:
    'That test case was not accepted, so it was not run. Write new cases.',
  invalid_setup:
    'The setup was not accepted. Check that the draft is not too long and that its template can be tested.',
  response_too_large:
    'The answer was too large to check, so this test was stopped.',
  revision_unusable:
    'The proposed revision was not usable, so nothing changed, though the call was still used. It may have been too long, tried to change more than the instructions, or copied a test into them. You can try again.',
  revision_unchanged:
    'The model proposed no change to the instructions, so nothing changed, though the call was still used. The failures may need a person to look at them.',
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
  path: 'agent-test-cases' | 'agent-test-runs' | 'agent-test-revisions',
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

export type FailedRun = { test: TestCase; run: CaseRun }

// The first failing run of each case, in case order.
export function failedRuns(
  cases: TestCase[],
  results: Record<string, CaseRun[]>,
): FailedRun[] {
  const failed: FailedRun[] = []
  for (const test of cases) {
    const run = results[test.id]?.find((item) => !item.passed)
    if (run) failed.push({ test, run })
  }
  return failed
}

// Counted in characters, not UTF-16 units, to match how the Lab counts.
const clip = (text: string, limit: number) =>
  [...text].length <= limit ? text : [...text].slice(0, limit).join('')

// What the Lab is told: the exact instructions that were tried and, for the
// first few failures, the case, the answer and the checks it missed. A model
// asked for a revision never sees the checks as anything it could edit.
export function revisionRequest(input: {
  instructions: string
  templateId: string
  failed: FailedRun[]
}) {
  return {
    instructions: input.instructions,
    template_id: input.templateId,
    failed: input.failed.slice(0, MAX_FAILED).map(({ test, run }) => ({
      case: test,
      text: clip(run.text, MAX_ANSWER),
      failures: run.failures.length
        ? run.failures.slice(0, 8).map((item) => clip(item, 300))
        : ['Did not pass the checks'],
    })),
    confirm_cost: true,
  }
}

export function parseRevision(value: unknown): Revision {
  const changes = isObject(value) ? strings(value.changes, 6) : null
  if (
    !isObject(value) ||
    typeof value.instructions !== 'string' ||
    ![...value.instructions.trim()].length ||
    [...value.instructions].length > 6000 ||
    !changes?.length
  )
    throw new Error('The revision response is invalid.')
  return {
    instructions: value.instructions,
    changes,
    usage: parseUsage(value.usage),
  }
}

// A case that passed every run before a revision and fails a run after it.
export function regressions(
  cases: TestCase[],
  before: Record<string, CaseRun[]>,
  after: Record<string, CaseRun[]>,
): string[] {
  return cases
    .filter((test) => {
      const was = before[test.id]
      return (
        !!was?.length &&
        was.every((run) => run.passed) &&
        !!after[test.id]?.some((run) => !run.passed)
      )
    })
    .map((test) => test.id)
}

// After a revision, run again every case that failed or never ran, plus a few
// that passed, so a change that fixed one answer and broke another shows up.
// The sample is the first passing cases in order, so the cost is predictable.
export function rerunScope(
  cases: TestCase[],
  results: Record<string, CaseRun[]>,
  sample = PASS_SAMPLE,
): string[] {
  const failed = new Set(failedRuns(cases, results).map((item) => item.test.id))
  const passed = cases
    .filter((test) => !failed.has(test.id) && results[test.id]?.length)
    .slice(0, sample)
    .map((test) => test.id)
  const keep = new Set([
    ...failed,
    ...passed,
    ...cases.filter((test) => !results[test.id]?.length).map((test) => test.id),
  ])
  return cases.filter((test) => keep.has(test.id)).map((test) => test.id)
}

// A line by line difference of two texts. Past a size where the comparison
// would be slow it shows the whole old text removed and the whole new text added.
export function lineDiff(before: string, after: string): DiffLine[] {
  const split = (text: string) => text.replace(/\r\n?/g, '\n').split('\n')
  const a = split(before)
  const b = split(after)
  if (a.length * b.length > 1_000_000)
    return [
      ...a.map((text): DiffLine => ({ kind: 'remove', text })),
      ...b.map((text): DiffLine => ({ kind: 'add', text })),
    ]
  // common[i][j]: lines in common between a[i..] and b[j..].
  const common = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0),
  )
  const at = (i: number, j: number) => common[i]?.[j] ?? 0
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--)
      common[i]![j] =
        a[i] === b[j]
          ? at(i + 1, j + 1) + 1
          : Math.max(at(i + 1, j), at(i, j + 1))
  const diff: DiffLine[] = []
  let i = 0
  let j = 0
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      diff.push({ kind: 'same', text: a[i]! })
      i++
      j++
    } else if (
      j >= b.length ||
      (i < a.length && at(i + 1, j) >= at(i, j + 1))
    ) {
      diff.push({ kind: 'remove', text: a[i]! })
      i++
    } else {
      diff.push({ kind: 'add', text: b[j]! })
      j++
    }
  }
  return diff
}

export const testFileName = (spec: Pick<AgentSpec, 'name'>) =>
  `${specSlug(spec)}.test-cases.json`

// One tried version of the instructions, the answers it got, and the reasons
// given for the revision a person accepted in its place.
export type Round = {
  instructions: string
  changes: string[]
  results: Record<string, CaseRun[]>
}

function fileRuns(cases: TestCase[], results: Record<string, CaseRun[]>) {
  return cases.flatMap((test) =>
    (results[test.id] ?? []).map((run) => ({
      case_id: run.case_id,
      passed: run.passed,
      failures: run.failures,
      answer: run.text,
      tools_called: run.receipts.map((receipt) => receipt.tool),
      elapsed_ms: run.elapsed_ms,
    })),
  )
}

// The cases and what came back, for a person to keep and to read against each
// rubric. The note travels with the file so a pass is never mistaken for proof.
export function testFile(input: {
  name: string
  templateId: string
  instructions: string
  cases: TestCase[]
  results: Record<string, CaseRun[]>
  rounds?: Round[]
}) {
  return {
    note: 'The automatic checks only screen answers. A person must read each answer against its rubric before relying on this agent.',
    agent: input.name,
    template_id: input.templateId,
    instructions: input.instructions,
    cases: input.cases,
    runs: fileRuns(input.cases, input.results),
    earlier_rounds: (input.rounds ?? []).map((round) => ({
      instructions: round.instructions,
      revised_because: round.changes,
      runs: fileRuns(input.cases, round.results),
    })),
  }
}
