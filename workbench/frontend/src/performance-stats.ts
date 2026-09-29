import type { Usage } from './token-usage'

export type Measurement = {
  id: string
  agent: string
  agentId: string
  outcome: 'completed' | 'failed' | 'stopped' | 'timed-out'
  duration: number
  at: number
  reference?: string
  message?: string
  usage?: Usage | null
}

export function percentile(values: number[], fraction: number) {
  if (!values.length) return null
  const sorted = [...values].sort((a, b) => a - b)
  return sorted[
    Math.min(sorted.length - 1, Math.ceil(fraction * sorted.length) - 1)
  ]
}
