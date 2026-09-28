import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  benchmarks,
  percentile,
  type Measurement,
} from '../src/performance-stats.ts'

const measurement = (
  agent: string,
  duration: number,
  outcome: Measurement['outcome'] = 'completed',
  agentId = agent,
): Measurement => ({
  id: `${agentId}-${duration}`,
  agent,
  agentId,
  outcome,
  duration,
  at: 0,
})

describe('performance stats', () => {
  it('uses nearest-rank percentiles', () => {
    assert.equal(percentile([], 0.5), null)
    assert.equal(percentile([30, 10, 20], 0.5), 20)
    assert.equal(percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.9), 9)
    assert.equal(percentile([5], 0.9), 5)
  })

  it('groups by agent in first-seen order and excludes unsuccessful timings', () => {
    const rows = benchmarks([
      measurement('Case checker', 4000),
      measurement('Grant checker', 1000),
      measurement('Case checker', 9000, 'timed-out'),
      measurement('Case checker', 2000),
    ])
    assert.deepEqual(
      rows.map((row) => row.agent),
      ['Case checker', 'Grant checker'],
    )
    assert.deepEqual(rows[0], {
      agentId: 'Case checker',
      agent: 'Case checker',
      requests: 3,
      completed: 2,
      median: 2000,
      p90: 4000,
      slowest: 4000,
      unsuccessful: 1,
      averageTokens: null,
    })
  })

  it('keeps agents with the same display name separate', () => {
    const rows = benchmarks([
      measurement('Document explainer', 1000, 'completed', 'created-a'),
      measurement('Document explainer', 5000, 'completed', 'created-b'),
    ])
    assert.deepEqual(
      rows.map((row) => [row.agentId, row.agent, row.median]),
      [
        ['created-a', 'Document explainer', 1000],
        ['created-b', 'Document explainer', 5000],
      ],
    )
  })

  it('averages only reported token totals from completed requests', () => {
    const usage = (total: number | null) => ({
      input_tokens: null,
      output_tokens: null,
      total_tokens: total,
      cached_tokens: null,
      reasoning_tokens: null,
    })
    const [row] = benchmarks([
      { ...measurement('Grant checker', 1000), usage: usage(100) },
      { ...measurement('Grant checker', 1200), usage: usage(301) },
      { ...measurement('Grant checker', 1300), usage: null },
      { ...measurement('Grant checker', 900, 'failed'), usage: usage(9000) },
    ])
    assert.equal(row.averageTokens, 201)
  })

  it('reports no timings when every request failed', () => {
    const [row] = benchmarks([measurement('Grant checker', 700, 'failed')])
    assert.equal(row.median, null)
    assert.equal(row.slowest, null)
    assert.equal(row.unsuccessful, 1)
  })
})
