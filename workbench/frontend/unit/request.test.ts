import assert from 'node:assert/strict'
import { afterEach, describe, it } from 'node:test'
import { errorBody, requestJson } from '../src/request.ts'
import { failureFromResponse } from '../src/chat-failure.ts'

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

  describe('error bodies', () => {
    it('keeps only string error codes and references', () => {
      assert.deepEqual(
        errorBody({ error: 'busy', request_id: 'sample-1', ignored: true }),
        { error: 'busy', request_id: 'sample-1' },
      )
      for (const value of [null, [], '', 503, true, undefined])
        assert.deepEqual(errorBody(value), {})
      assert.deepEqual(errorBody({ error: [], request_id: 1 }), {
        error: undefined,
        request_id: undefined,
      })
    })

    it('keeps HTTP errors distinct from connection failures', () => {
      for (const value of [null, [], 'error', 503, true]) {
        const failure = failureFromResponse(
          new Response('', {
            status: 503,
            headers: { 'X-Correlation-ID': 'sample-reference' },
          }),
          value,
        )
        assert.match(failure.message, /could not get a reply from its service/)
        assert.equal(failure.reference, 'sample-reference')
        assert.match(failure.details, /HTTP 503/)
      }
    })
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

  it('propagates cancellation to the underlying fetch', async () => {
    let aborted = false
    const unrelated = new AbortController()
    globalThis.fetch = (_url, options) =>
      new Promise<Response>((_resolve, reject) => {
        options?.signal?.addEventListener(
          'abort',
          () => {
            aborted = true
            reject(new DOMException('Aborted', 'AbortError'))
          },
          { once: true },
        )
      })
    const abort = new AbortController()
    const pending = requestJson(
      '/api/config',
      { signal: unrelated.signal },
      abort.signal,
    )
    abort.abort()
    await assert.rejects(pending, { name: 'AbortError' })
    assert.equal(aborted, true)
    assert.equal(unrelated.signal.aborted, false)
  })

  it('stops waiting while the response body is still streaming', async () => {
    let reading = () => {}
    const started = new Promise<void>((resolve) => {
      reading = resolve
    })
    globalThis.fetch = async () => {
      const response = new Response('{}')
      response.text = () => {
        reading()
        return new Promise<string>(() => {})
      }
      return response
    }
    const abort = new AbortController()
    const pending = requestJson('/api/config', {}, abort.signal)
    await started
    abort.abort()
    await assert.rejects(pending, { name: 'AbortError' })
  })
})
