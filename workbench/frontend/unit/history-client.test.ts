import assert from 'node:assert/strict'
import { afterEach, beforeEach, describe, it } from 'node:test'
import { createElement } from 'react'
import { renderToString } from 'react-dom/server'
import { useHistoryClient } from '../src/history-client.ts'

const originalFetch = globalThis.fetch
const hadWindow = 'window' in globalThis

beforeEach(() => {
  if (!hadWindow) Object.assign(globalThis, { window: globalThis })
})

afterEach(() => {
  globalThis.fetch = originalFetch
  if (!hadWindow) Reflect.deleteProperty(globalThis, 'window')
})

function respond(body: string, status: number) {
  globalThis.fetch = async () => new Response(body, { status })
}

// Hooks only run inside a component, so render a probe to get the request function.
function historyRequest(timeoutMs: number | undefined) {
  const captured: ReturnType<typeof useHistoryClient>[] = []
  const Probe = () => {
    captured.push(useHistoryClient(timeoutMs))
    return null
  }
  renderToString(createElement(Probe))
  return captured[0]
}

const unavailable =
  'Saved history is unavailable. Your local messages are unchanged.'

describe('useHistoryClient', () => {
  it('returns the parsed body of a successful response', async () => {
    respond('{"turns":[]}', 200)
    assert.deepEqual(await historyRequest(5000)(''), { turns: [] })
  })

  it('maps known error codes to their messages', async () => {
    respond('{"error":"conversation_not_found"}', 404)
    await assert.rejects(historyRequest(5000)('/abc'), {
      message:
        'This shared conversation was deleted or expired. Your local messages are unchanged.',
    })
  })

  it('uses the generic message for an unknown error code', async () => {
    respond('{"error":"something_new"}', 500)
    await assert.rejects(historyRequest(5000)('/abc'), { message: unavailable })
  })

  it('uses the generic message for a non-JSON error body', async () => {
    respond('<html><body>502 Bad Gateway</body></html>', 502)
    await assert.rejects(historyRequest(5000)('/abc'), { message: unavailable })
  })

  it('uses the generic message for an empty error body', async () => {
    respond('', 504)
    await assert.rejects(historyRequest(5000)('/abc'), { message: unavailable })
  })

  it('rejects an unreadable successful response with a plain message', async () => {
    respond('<html>Welcome</html>', 200)
    await assert.rejects(historyRequest(5000)('/abc'), {
      message: 'The server returned an unreadable response.',
    })
    respond('', 200)
    await assert.rejects(historyRequest(5000)('/abc'), {
      message: 'The server returned an unreadable response.',
    })
  })

  it('refuses to send a request without workspace configuration', async () => {
    await assert.rejects(historyRequest(undefined)('/abc'), {
      message: 'Workspace configuration is unavailable.',
    })
  })
})
