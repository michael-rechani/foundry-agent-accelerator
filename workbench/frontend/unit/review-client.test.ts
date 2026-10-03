import assert from 'node:assert/strict'
import { afterEach, describe, it } from 'node:test'
import { reviewRequest } from '../src/review-client.ts'

const originalFetch = globalThis.fetch

afterEach(() => {
  globalThis.fetch = originalFetch
})

function respond(body: string, status: number) {
  globalThis.fetch = async () => new Response(body, { status })
}

const generic =
  'The request could not be confirmed. Refresh the inbox before repeating an action.'

describe('reviewRequest', () => {
  it('returns the parsed body of a successful response', async () => {
    respond('{"items":[],"cursor":null}', 200)
    assert.deepEqual(await reviewRequest(''), { items: [], cursor: null })
  })

  it('sends the Lab header, method, body and etag', async () => {
    let received: RequestInit | undefined
    globalThis.fetch = async (_url, options) => {
      received = options
      return new Response('{}')
    }
    await reviewRequest('/review-1', 'POST', { confirm_cost: true }, '3')
    const headers = received?.headers as Record<string, string>
    assert.equal(received?.method, 'POST')
    assert.equal(received?.body, '{"confirm_cost":true}')
    assert.equal(headers['X-Workbench-Request'], '1')
    assert.equal(headers['Content-Type'], 'application/json')
    assert.equal(headers['If-Match'], '3')
  })

  it('maps known error codes to their messages', async () => {
    respond('{"error":"review_changed"}', 409)
    await assert.rejects(reviewRequest('/review-1'), {
      message: 'This review changed. Refresh before continuing.',
    })
  })

  it('says plainly when a review does not exist', async () => {
    respond('{"error":"not_found"}', 404)
    await assert.rejects(reviewRequest('/review-1'), {
      message:
        'That review could not be found. It may have been removed, or the link may be wrong.',
    })
  })

  it('uses the generic message for an unknown error code', async () => {
    respond('{"error":"something_new"}', 500)
    await assert.rejects(reviewRequest('/review-1'), { message: generic })
  })

  it('uses the generic message for a non-JSON error body', async () => {
    respond('<html><body>502 Bad Gateway</body></html>', 502)
    await assert.rejects(reviewRequest('/review-1'), { message: generic })
  })

  it('uses the generic message for an empty error body', async () => {
    respond('', 504)
    await assert.rejects(reviewRequest('/review-1'), { message: generic })
  })

  it('rejects an unreadable successful response with a plain message', async () => {
    respond('<html>Welcome</html>', 200)
    await assert.rejects(reviewRequest('/review-1'), {
      message: 'The server returned an unreadable response.',
    })
    respond('', 200)
    await assert.rejects(reviewRequest('/review-1'), {
      message: 'The server returned an unreadable response.',
    })
  })
})
