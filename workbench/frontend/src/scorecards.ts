// Parsing and plain-language formatting for recorded test results (scorecards).
// Uses erasable TypeScript only so `node --test` can import it directly.

export type ScorecardCase = {
  id: string
  category: string
  goal: string
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
  answers_from: 'lab' | 'rerun' | 'mixed'
  signed_off: boolean
  summary: {
    cases: number
    passed: number
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

function validCase(item: unknown): item is ScorecardCase {
  return (
    isObject(item) &&
    text(item.id) &&
    text(item.category) &&
    item.category in categoryTitles &&
    text(item.goal) &&
    typeof item.passed === 'boolean' &&
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
    ['lab', 'rerun', 'mixed'].includes(String(item.answers_from)) &&
    typeof item.signed_off === 'boolean' &&
    Array.isArray(cases) &&
    cases.length > 0 &&
    cases.every(validCase) &&
    summary.cases === cases.length &&
    summary.passed === cases.filter((entry) => entry.passed).length &&
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
