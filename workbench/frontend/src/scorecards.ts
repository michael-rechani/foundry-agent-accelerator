// Parsing and plain-language formatting for recorded test results (scorecards).
// Uses erasable TypeScript only so `node --test` can import it directly.

export type ScorecardCase = {
  id: string
  category: string
  goal: string
  input: string
  runs: number
  runs_passed: number
  passed: boolean
  notes: string[]
  seconds: number
  input_tokens: number
  cached_tokens: number
  output_tokens: number
  cost_usd: number
}

export type Scorecard = {
  template_id: string
  tested_on: string
  model: string
  answers_from: 'lab' | 'direct' | 'mixed'
  signed_off: boolean
  signed_off_by: string | null
  signed_off_on: string | null
  summary: {
    cases: number
    passed: number
    runs_per_case: number
    runs: number
    runs_passed: number
    median_seconds: number
    average_cost_usd: number
  }
  cases: ScorecardCase[]
}

export type Scorecards = {
  answers_dataset: string
  checks_dataset: string
  prices: {
    currency: string
    retrieved_on: string
    source: string
    region: string
    deployment_type: string
  }
  scorecards: Scorecard[]
}

export const categoryTitles: Record<string, string> = {
  grounded: "Sticks to the facts it's given",
  missing: 'Asks for missing information',
  conflict: 'Points out information that disagrees',
  injection: 'Ignores instructions hidden in the input',
  'decision-boundary': 'Leaves the decision to a person',
}

function isObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function text(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function amount(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0
}

function count(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
}

function validCase(item: unknown): item is ScorecardCase {
  return (
    isObject(item) &&
    text(item.id) &&
    text(item.category) &&
    item.category in categoryTitles &&
    text(item.goal) &&
    text(item.input) &&
    count(item.runs) &&
    item.runs >= 1 &&
    count(item.runs_passed) &&
    item.runs_passed <= item.runs &&
    typeof item.passed === 'boolean' &&
    item.passed === (item.runs_passed === item.runs) &&
    Array.isArray(item.notes) &&
    item.notes.every(text) &&
    item.passed === (item.notes.length === 0) &&
    ['seconds', 'input_tokens', 'cached_tokens', 'output_tokens', 'cost_usd']
      .map((key) => item[key])
      .every(amount)
  )
}

function validScorecard(item: unknown): item is Scorecard {
  if (!isObject(item) || !isObject(item.summary)) return false
  const summary = item.summary
  const cases = item.cases
  return (
    text(item.template_id) &&
    /^\d{4}-\d{2}-\d{2}$/.test(String(item.tested_on)) &&
    text(item.model) &&
    ['lab', 'direct', 'mixed'].includes(String(item.answers_from)) &&
    typeof item.signed_off === 'boolean' &&
    (item.signed_off
      ? text(item.signed_off_by) &&
        /^\d{4}-\d{2}-\d{2}$/.test(String(item.signed_off_on))
      : item.signed_off_by === null && item.signed_off_on === null) &&
    Array.isArray(cases) &&
    cases.length > 0 &&
    cases.every(validCase) &&
    summary.cases === cases.length &&
    summary.passed === cases.filter((entry) => entry.passed).length &&
    count(summary.runs_per_case) &&
    summary.runs_per_case >= 1 &&
    summary.runs === cases.reduce((total, entry) => total + entry.runs, 0) &&
    summary.runs === cases.length * summary.runs_per_case &&
    summary.runs_passed ===
      cases.reduce((total, entry) => total + entry.runs_passed, 0) &&
    amount(summary.median_seconds) &&
    amount(summary.average_cost_usd)
  )
}

export function parseScorecards(value: unknown): Scorecards {
  if (
    !isObject(value) ||
    value.schema_version !== 1 ||
    !text(value.answers_dataset) ||
    !text(value.checks_dataset) ||
    !isObject(value.prices) ||
    !['currency', 'retrieved_on', 'source', 'region', 'deployment_type'].every(
      (key) => text((value.prices as Record<string, unknown>)[key]),
    ) ||
    !Array.isArray(value.scorecards) ||
    !value.scorecards.every(validScorecard)
  )
    throw new Error('The test results could not be read.')
  const ids = value.scorecards.map((card) => card.template_id)
  if (new Set(ids).size !== ids.length)
    throw new Error('The test results could not be read.')
  return value as Scorecards
}

export function formatDate(iso: string) {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString('en-US', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

// "5 of 5 answers passed": one answer per run of a test case.
export function formatAnswersPassed(passed: number, runs: number) {
  return `${passed} of ${runs} ${runs === 1 ? 'answer' : 'answers'} passed`
}

export function formatTimes(runs: number) {
  return runs === 1 ? 'once' : `${runs} times`
}

const MAX_ANSWER_DOTS = 10

// One dot per answer, passes first. A scorecard says how many answers passed,
// not which ones, so the order carries no meaning. A case asked more often than
// the row can show gets no dots; its sentence still says it all.
export function answerDots(passed: number, runs: number): boolean[] {
  if (!Number.isInteger(runs) || runs < 1 || runs > MAX_ANSWER_DOTS) return []
  return Array.from({ length: runs }, (_, index) => index < passed)
}

export function formatSeconds(value: number) {
  return `${value.toFixed(1)} s`
}

// Customer-facing: rounded to whole cents so it reads as a rough guide.
export function formatCostPerAnswer(usd: number) {
  const cents = usd * 100
  if (cents < 1) return 'Under 1¢'
  if (usd < 1) return `About ${Math.round(cents)}¢`
  return `About $${usd.toFixed(2)}`
}

export function formatExactCost(usd: number) {
  return `$${usd.toFixed(4)}`
}
