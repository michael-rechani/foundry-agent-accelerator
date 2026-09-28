import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  estimateCost,
  parseRates,
  parseUsage,
  totalUsage,
  usageDetail,
  usageLabel,
} from '../src/token-usage.ts'

const reported = {
  input_tokens: 1200,
  output_tokens: 300,
  total_tokens: 1500,
  cached_tokens: 200,
  reasoning_tokens: 120,
}

describe('token usage', () => {
  it('keeps only non-negative integer counts and treats all-missing as unreported', () => {
    assert.deepEqual(parseUsage(reported), reported)
    assert.equal(parseUsage(null), null)
    assert.equal(parseUsage({ total_tokens: -1, input_tokens: 'x' }), null)
    assert.deepEqual(parseUsage({ total_tokens: 7, input_tokens: 1.5 }), {
      input_tokens: null,
      output_tokens: null,
      total_tokens: 7,
      cached_tokens: null,
      reasoning_tokens: null,
    })
  })

  it('labels missing usage as not reported, never zero', () => {
    assert.equal(usageLabel(undefined), null)
    assert.equal(usageLabel(null), 'Tokens not reported')
    assert.equal(usageLabel(reported), '1,500 tokens')
    assert.equal(
      usageDetail(reported),
      '1,200 in (200 cached) · 300 out (120 reasoning) · 1,500 total',
    )
    assert.equal(
      usageDetail({ ...reported, output_tokens: null, reasoning_tokens: null }),
      '1,200 in (200 cached) · out not reported · 1,500 total',
    )
  })

  it('totals reported replies and counts the rest as missing', () => {
    assert.deepEqual(totalUsage([reported, null, reported]), {
      input: 2400,
      output: 600,
      total: 3000,
      measured: 2,
      missing: 1,
    })
  })

  it('estimates from user rates per million tokens', () => {
    assert.equal(
      estimateCost(
        { input: 2_000_000, output: 500_000 },
        { input: 2, output: 8 },
      ),
      8,
    )
    assert.deepEqual(parseRates({ input: 0, output: 1.5 }), {
      input: 0,
      output: 1.5,
    })
    for (const bad of [
      null,
      { input: -1, output: 1 },
      { input: 1 },
      { input: NaN, output: 1 },
    ])
      assert.equal(parseRates(bad), null)
  })
})
