import assert from 'node:assert/strict'
import { afterEach, describe, it } from 'node:test'
import { requestJson } from '../src/request.ts'

const originalFetch = globalThis.fetch

afterEach(() => {
  globalThis.fetch = originalFetch
})

function respond(body: string, status = 200) {
  globalThis.fetch = async () => new Response(body, { status })
}

describe('requestJson', () => {
  it('returns the response with its parsed body', async () => {
    let received: RequestInit | undefined
    globalThis.fetch = async (_url, options) => {
      received = options
      return new Response('{"ok":true}')
    }
    const signal = new AbortController().signal
    const { response, data } = await requestJson(
      '/api/config',
      { method: 'POST' },
      signal,
    )
    assert.equal(response.status, 200)
    assert.deepEqual(data, { ok: true })
    assert.equal(received?.method, 'POST')
    assert.equal(received?.signal, signal)
  })

  it('returns an empty body for unreadable error responses', async () => {
    respond('<html>Bad gateway</html>', 502)
    const { response, data } = await requestJson(
      '/api/config',
      {},
      new AbortController().signal,
    )
    assert.equal(response.status, 502)
    assert.deepEqual(data, {})
  })

  it('rejects unreadable successful responses', async () => {
    respond('')
    await assert.rejects(
      requestJson('/api/config', {}, new AbortController().signal),
      { message: 'The server returned an unreadable response.' },
    )
  })

  it('does not send a request after cancellation', async () => {
    let called = false
    globalThis.fetch = async () => {
      called = true
      return new Response('{}')
    }
    const abort = new AbortController()
    abort.abort()
    await assert.rejects(requestJson('/api/config', {}, abort.signal), {
      name: 'AbortError',
    })
    assert.equal(called, false)
  })

  it('stops waiting when cancelled, even if fetch ignores the signal', async () => {
    globalThis.fetch = () => new Promise<Response>(() => {})
    const abort = new AbortController()
    const pending = requestJson('/api/config', {}, abort.signal)
    abort.abort()
    await assert.rejects(pending, { name: 'AbortError' })
  })
})
