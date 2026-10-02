import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { reviewIdFromHash } from '../src/review-client.ts'

const id = 'review-12345678-1234-1234-1234-123456789abc'

describe('reviewIdFromHash', () => {
  it('returns the review id from a saved review link', () => {
    assert.equal(reviewIdFromHash('#' + id), id)
  })

  it('ignores page links and anything that is not a review id', () => {
    for (const hash of [
      '',
      '#',
      '#reviews',
      '#chat',
      id,
      '#review-not-a-valid-id',
      '#review-12345678-1234-1234-1234-123456789ab',
      '#review-12345678-1234-1234-1234-123456789abcd',
      '#review-1234567G-1234-1234-1234-123456789abc',
      '#' + id.toUpperCase(),
      '#' + id + '/extra',
      ' #' + id,
    ]) {
      assert.equal(reviewIdFromHash(hash), null, hash)
    }
  })
})
