export type Measurement = {
  id: string
  agent: string
  agentId: string
  outcome: 'completed' | 'failed' | 'stopped' | 'timed-out'
  duration: number
  at: number
  reference?: string
  message?: string
}

export function percentile(values: number[], fraction: number) {
  if (!values.length) return null
  const sorted = [...values].sort((a, b) => a - b)
  return sorted[
    Math.min(sorted.length - 1, Math.ceil(fraction * sorted.length) - 1)
  ]
}

export function benchmarks(measurements: Measurement[]) {
  const groups = new Map<string, Measurement[]>()
  for (const item of measurements)
    groups.set(item.agentId, [...(groups.get(item.agentId) ?? []), item])
  return [...groups].map(([agentId, items]) => {
    const durations = items
      .filter((item) => item.outcome === 'completed')
      .map((item) => item.duration)
    return {
      agentId,
      agent: items[0].agent,
      requests: items.length,
      completed: durations.length,
      median: percentile(durations, 0.5),
      p90: percentile(durations, 0.9),
      slowest: durations.length ? Math.max(...durations) : null,
      unsuccessful: items.length - durations.length,
    }
  })
}
