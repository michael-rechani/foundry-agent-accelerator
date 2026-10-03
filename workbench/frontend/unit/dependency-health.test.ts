import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { parseDependencyHealth } from '../src/dependency-health.ts'

describe('dependency health', () => {
  it('reads a healthy report', () => {
    assert.deepEqual(
      parseDependencyHealth({
        status: 'ready',
        foundry: 'ready',
        cosmos: 'ready',
      }),
      { status: 'ready', foundry: 'ready', cosmos: 'ready' },
    )
  })

  it('shows a failed probe as needing attention, not as unchecked', () => {
    assert.deepEqual(
      parseDependencyHealth({
        status: 'degraded',
        foundry: 'unavailable',
        cosmos: 'ready',
      }),
      { status: 'degraded', foundry: 'degraded', cosmos: 'ready' },
    )
  })

  it('lets each service follow the overall status while starting', () => {
    assert.deepEqual(parseDependencyHealth({ status: 'starting' }), {
      status: 'starting',
      foundry: 'starting',
      cosmos: 'starting',
    })
  })

  it('shows services as off in a preview without live connections', () => {
    assert.deepEqual(parseDependencyHealth({ status: 'disabled' }), {
      status: 'disabled',
      foundry: 'disabled',
      cosmos: 'disabled',
    })
  })

  it('keeps history off when only it is disabled', () => {
    assert.deepEqual(
      parseDependencyHealth({
        status: 'ready',
        foundry: 'ready',
        cosmos: 'disabled',
      }),
      { status: 'ready', foundry: 'ready', cosmos: 'disabled' },
    )
  })

  it('treats anything unrecognised as unknown', () => {
    const unknown = { status: 'unknown', foundry: 'unknown', cosmos: 'unknown' }
    assert.deepEqual(parseDependencyHealth(null), unknown)
    assert.deepEqual(parseDependencyHealth({}), unknown)
    assert.deepEqual(parseDependencyHealth('ready'), unknown)
    assert.deepEqual(
      parseDependencyHealth({ status: 'ready', foundry: 7, cosmos: [] }),
      { status: 'ready', foundry: 'unknown', cosmos: 'unknown' },
    )
  })
})
