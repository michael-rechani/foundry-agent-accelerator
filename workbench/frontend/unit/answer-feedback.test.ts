import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  maxReasonLength,
  summarizeRatings,
  withRating,
} from '../src/answer-feedback.ts'
import type { Turn } from '../src/conversation-types.ts'

const turn = (question: string, rating?: Turn['rating']): Turn => ({
  question,
  rating,
  result: {
    request_id: question,
    agent: 'a',
    text: 'answer',
    receipts: [],
    elapsed_ms: 1,
  },
})

describe('answer feedback', () => {
  it('rates only the chosen answer and can change or clear it', () => {
    const turns = [turn('one'), turn('two')]
    const rated = withRating(turns, 1, { value: 'up' })
    assert.equal(rated[0].rating, undefined)
    assert.deepEqual(rated[1].rating, { value: 'up' })
    const changed = withRating(rated, 1, {
      value: 'down',
      reason: 'Wrong total',
    })
    assert.deepEqual(changed[1].rating, {
      value: 'down',
      reason: 'Wrong total',
    })
    const cleared = withRating(changed, 1, undefined)
    assert.equal('rating' in cleared[1], false)
    assert.equal(turns[1].rating, undefined)
  })

  it('drops an empty reason and caps a long one', () => {
    const [empty] = withRating([turn('one')], 0, { value: 'up', reason: '' })
    assert.deepEqual(empty.rating, { value: 'up' })
    const [long] = withRating([turn('one')], 0, {
      value: 'down',
      reason: 'x'.repeat(maxReasonLength + 50),
    })
    assert.equal(long.rating?.reason?.length, maxReasonLength)
  })

  it('summarizes ratings for the side panel', () => {
    assert.equal(summarizeRatings([turn('one'), turn('two')]), '')
    assert.equal(
      summarizeRatings([
        turn('1', { value: 'up' }),
        turn('2', { value: 'up' }),
        turn('3', { value: 'down' }),
        turn('4'),
      ]),
      '2 helpful, 1 not helpful',
    )
    assert.equal(
      summarizeRatings([turn('1', { value: 'down' })]),
      '1 not helpful',
    )
  })
})
