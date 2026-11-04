import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { viewForHash, viewHashes } from '../src/navigation.ts'

describe('workspace links', () => {
  it('round-trips every workspace view', () => {
    for (const [view, hash] of Object.entries(viewHashes))
      assert.equal(viewForHash(hash), view)
  })

  it('keeps legacy and saved-review links', () => {
    assert.equal(viewForHash('#start'), 'library')
    assert.equal(
      viewForHash('#review-12345678-1234-1234-1234-123456789abc'),
      'reviews',
    )
  })

  it('opens Chat for an empty or unrecognized hash', () => {
    assert.equal(viewForHash(''), 'chat')
    assert.equal(viewForHash('#unknown'), 'chat')
  })
})
