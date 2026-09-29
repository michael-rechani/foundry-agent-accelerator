import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { percentile } from '../src/performance-stats.ts'

describe('performance stats', () => {
  it('uses nearest-rank percentiles', () => {
    assert.equal(percentile([], 0.5), null)
    assert.equal(percentile([30, 10, 20], 0.5), 20)
    assert.equal(percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.9), 9)
    assert.equal(percentile([5], 0.9), 5)
  })
})
