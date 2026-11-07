import type { Usage } from './token-usage'

export type ModelCall = {
  reported_model: string | null
  model_status: 'reported' | 'not_reported' | 'invalid'
  usage: Usage | null
}

export type ModelObservation = {
  deployment: string
  calls: ModelCall[]
}

const deploymentName = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/
const reportedModelName = /^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$/
// Must match the server's MAX_TOOL_ROUNDS + 1.
const maxCalls = 5
const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
const matchesExactly = (pattern: RegExp, value: string) =>
  pattern.exec(value)?.[0] === value
const tokenCount = (value: unknown): value is number | null =>
  value === null ||
  (typeof value === 'number' && Number.isSafeInteger(value) && value >= 0)

function observedUsage(value: unknown): Usage | null | undefined {
  if (value === null) return null
  if (!record(value)) return undefined
  const {
    input_tokens,
    output_tokens,
    total_tokens,
    cached_tokens,
    reasoning_tokens,
  } = value
  if (
    !tokenCount(input_tokens) ||
    !tokenCount(output_tokens) ||
    !tokenCount(total_tokens) ||
    !tokenCount(cached_tokens) ||
    !tokenCount(reasoning_tokens)
  )
    return undefined
  return {
    input_tokens,
    output_tokens,
    total_tokens,
    cached_tokens,
    reasoning_tokens,
  }
}

export function parseModelObservation(value: unknown): ModelObservation | null {
  if (
    !record(value) ||
    typeof value.deployment !== 'string' ||
    !matchesExactly(deploymentName, value.deployment) ||
    !Array.isArray(value.calls) ||
    value.calls.length < 1 ||
    value.calls.length > maxCalls
  )
    return null
  const calls: ModelCall[] = []
  for (const call of value.calls) {
    if (!record(call)) return null
    const { reported_model, model_status } = call
    if (
      model_status !== 'reported' &&
      model_status !== 'not_reported' &&
      model_status !== 'invalid'
    )
      return null
    let model: string | null
    if (model_status === 'reported') {
      if (
        typeof reported_model !== 'string' ||
        !matchesExactly(reportedModelName, reported_model)
      )
        return null
      model = reported_model
    } else {
      if (reported_model !== null) return null
      model = null
    }
    const usage = observedUsage(call.usage)
    if (usage === undefined) return null
    calls.push({
      reported_model: model,
      model_status,
      usage,
    })
  }
  return { deployment: value.deployment, calls }
}

export function readModelObservation(value: unknown, isDirectPreview: boolean) {
  const observation = isDirectPreview ? parseModelObservation(value) : null
  return {
    observation,
    invalid: value !== undefined && value !== null && observation === null,
  }
}
