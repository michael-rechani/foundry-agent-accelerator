export type Usage = {
  input_tokens: number | null
  output_tokens: number | null
  total_tokens: number | null
  cached_tokens: number | null
  reasoning_tokens: number | null
}

// Prices per one million tokens that the user types in; never shipped with the Lab.
export type Rates = { input: number; output: number }

const fields = [
  'input_tokens',
  'output_tokens',
  'total_tokens',
  'cached_tokens',
  'reasoning_tokens',
] as const

const count = (value: unknown) =>
  typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
    ? value
    : null

/** Returns reported token counts, or null when the reply reported none. */
export function parseUsage(value: unknown): Usage | null {
  if (!value || typeof value !== 'object') return null
  const source = value as Record<string, unknown>
  const usage = Object.fromEntries(
    fields.map((field) => [field, count(source[field])]),
  ) as Usage
  return fields.some((field) => usage[field] !== null) ? usage : null
}

export const formatTokens = (value: number) => value.toLocaleString('en-US')

export function usageLabel(usage: Usage | null | undefined) {
  if (usage === undefined) return null
  return usage?.total_tokens != null
    ? `${formatTokens(usage.total_tokens)} tokens`
    : 'Tokens not reported'
}

export function usageDetail(usage: Usage) {
  const part = (value: number | null, label: string, extra?: string) =>
    value === null
      ? `${label} not reported`
      : `${formatTokens(value)} ${label}${extra ?? ''}`
  return [
    part(
      usage.input_tokens,
      'in',
      usage.cached_tokens
        ? ` (${formatTokens(usage.cached_tokens)} cached)`
        : '',
    ),
    part(
      usage.output_tokens,
      'out',
      usage.reasoning_tokens
        ? ` (${formatTokens(usage.reasoning_tokens)} reasoning)`
        : '',
    ),
    part(usage.total_tokens, 'total'),
  ].join(' · ')
}

/** Sums reported tokens. Replies without a count are tallied, not treated as zero. */
export function totalUsage(items: (Usage | null)[]) {
  let input = 0
  let output = 0
  let total = 0
  let missing = 0
  for (const usage of items) {
    if (
      usage?.input_tokens == null ||
      usage.output_tokens == null ||
      usage.total_tokens == null
    ) {
      missing += 1
      continue
    }
    input += usage.input_tokens
    output += usage.output_tokens
    total += usage.total_tokens
  }
  return { input, output, total, measured: items.length - missing, missing }
}

/** Estimate at the user's rates. Cached input is priced at the full input rate, so it can overstate. */
export function estimateCost(
  totals: { input: number; output: number },
  rates: Rates,
) {
  return (totals.input * rates.input + totals.output * rates.output) / 1_000_000
}

export function parseRates(value: unknown): Rates | null {
  if (!value || typeof value !== 'object') return null
  const { input, output } = value as Record<string, unknown>
  const valid = (rate: unknown) =>
    typeof rate === 'number' && Number.isFinite(rate) && rate >= 0 && rate < 1e6
  return valid(input) && valid(output)
    ? { input: input as number, output: output as number }
    : null
}

const RATES_KEY = 'foundry-lab-token-rates'

export function loadRates(): Rates | null {
  try {
    return parseRates(JSON.parse(localStorage.getItem(RATES_KEY) ?? 'null'))
  } catch {
    return null
  }
}

export function storeRates(rates: Rates | null) {
  try {
    if (rates) localStorage.setItem(RATES_KEY, JSON.stringify(rates))
    else localStorage.removeItem(RATES_KEY)
  } catch {
    // Storage can be unavailable in private browsing; the estimate still works for this tab.
  }
}
