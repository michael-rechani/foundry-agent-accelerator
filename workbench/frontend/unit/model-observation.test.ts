import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  parseModelObservation,
  readModelObservation,
} from '../src/model-observation.ts'

const usage = {
  input_tokens: 100,
  output_tokens: 20,
  total_tokens: 120,
  cached_tokens: 0,
  reasoning_tokens: null,
}
const call = {
  reported_model: 'gpt-4.1',
  model_status: 'reported',
  usage,
}
const observation = {
  deployment: 'model-router',
  calls: [
    call,
    { reported_model: null, model_status: 'not_reported', usage: null },
    { reported_model: null, model_status: 'invalid', usage: null },
  ],
}

describe('direct model observations', () => {
  it('keeps bounded, reported calls and nullable token counts', () => {
    assert.deepEqual(parseModelObservation(observation), observation)
    assert.deepEqual(
      parseModelObservation({
        ...observation,
        extra: 'ignored',
        calls: [{ ...call, extra: 'ignored' }],
      }),
      { deployment: 'model-router', calls: [call] },
    )
    assert.deepEqual(readModelObservation(observation, true), {
      observation,
      invalid: false,
    })
  })

  it('rejects malformed or inconsistent names, usage and call counts', () => {
    for (const bad of [
      null,
      { ...observation, deployment: 'invalid\nname' },
      { ...observation, deployment: 'model-router\n' },
      { ...observation, deployment: 'a'.repeat(129) },
      { ...observation, calls: [] },
      { ...observation, calls: Array(6).fill(call) },
      { ...observation, calls: [{ ...call, reported_model: null }] },
      { ...observation, calls: [{ ...call, reported_model: 'bad\nname' }] },
      { ...observation, calls: [{ ...call, reported_model: 'gpt-4.1\n' }] },
      { ...observation, calls: [{ ...call, model_status: 'not_reported' }] },
      { ...observation, calls: [{ ...call, model_status: 'unknown' }] },
      {
        ...observation,
        calls: [{ ...call, usage: { ...usage, input_tokens: -1 } }],
      },
      {
        ...observation,
        calls: [{ ...call, usage: { ...usage, output_tokens: true } }],
      },
      { ...observation, calls: [{ ...call, usage: { input_tokens: 100 } }] },
    ])
      assert.equal(parseModelObservation(bad), null)
  })

  it('does not attribute hosted or malformed replies and accepts legacy replies', () => {
    assert.deepEqual(readModelObservation(observation, false), {
      observation: null,
      invalid: true,
    })
    assert.deepEqual(readModelObservation({ bad: true }, true), {
      observation: null,
      invalid: true,
    })
    for (const missing of [undefined, null])
      assert.deepEqual(readModelObservation(missing, true), {
        observation: null,
        invalid: false,
      })
  })
})
