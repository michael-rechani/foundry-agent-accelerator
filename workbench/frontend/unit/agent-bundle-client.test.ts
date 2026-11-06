import assert from 'node:assert/strict'
import { afterEach, describe, it } from 'node:test'
import {
  BundleError,
  bundleFileName,
  bundleRequest,
  fetchBundle,
} from '../src/agent-bundle-client.ts'
import type { AgentSpec } from '../src/agent-spec.ts'

const originalFetch = globalThis.fetch

afterEach(() => {
  globalThis.fetch = originalFetch
})

const spec: AgentSpec = {
  name: 'Renewal Checklist Helper!',
  summary: 'Turns a renewal notice into a short checklist.',
  instructions: 'List what the person must send before the renewal date.',
  inputs: 'A renewal notice',
  outputs: 'A checklist',
  tools_needed: ['lookup_case'],
  human_decision: 'A caseworker decides eligibility.',
  closest_template: null,
}

describe('bundleFileName and bundleRequest', () => {
  it('name the file and the agent after the same slug as the spec download', () => {
    assert.equal(
      bundleFileName(spec),
      'renewal-checklist-helper.agent-bundle.zip',
    )
    assert.equal(bundleRequest(spec).name, 'renewal-checklist-helper')
    assert.equal(bundleFileName({ name: '???' }), 'agent.agent-bundle.zip')
  })

  it('sends only the summary and the instructions of the spec', () => {
    assert.deepEqual(bundleRequest(spec), {
      name: 'renewal-checklist-helper',
      description: spec.summary,
      instructions: spec.instructions,
    })
  })
})

describe('fetchBundle', () => {
  const zip = (body: BodyInit = 'PK-bundle') =>
    new Response(body, {
      headers: { 'Content-Type': 'application/zip' },
    })

  function respond(body: string, status: number, headers: HeadersInit = {}) {
    globalThis.fetch = async () => new Response(body, { status, headers })
  }

  it('posts JSON with the Lab header and returns the file', async () => {
    let url = ''
    let received: RequestInit | undefined
    globalThis.fetch = async (input, options) => {
      url = String(input)
      received = options
      return zip(new Uint8Array([80, 75, 3, 4]))
    }
    const file = await fetchBundle(spec)
    const headers = received?.headers as Record<string, string>
    assert.deepEqual(
      new Uint8Array(await file.arrayBuffer()),
      new Uint8Array([80, 75, 3, 4]),
    )
    assert.equal(url, '/api/agent-bundles')
    assert.equal(received?.method, 'POST')
    assert.equal(received?.body, JSON.stringify(bundleRequest(spec)))
    assert.equal(headers['X-Workbench-Request'], '1')
    assert.equal(headers['Content-Type'], 'application/json')
  })

  it('explains a spec the Lab did not accept, with the request reference', async () => {
    respond('{"error":"invalid_bundle","request_id":"r-1"}', 400)
    await assert.rejects(
      fetchBundle(spec),
      (problem) =>
        problem instanceof BundleError &&
        /at least 10 characters/.test(problem.failure.message) &&
        problem.failure.reference === 'r-1',
    )
  })

  it('uses the shared message for codes the chat already explains', async () => {
    respond('{"error":"library_preview_disabled"}', 503)
    await assert.rejects(fetchBundle(spec), {
      message: /Library previews are turned off/,
    })
  })

  it('does not treat an error page as a bundle', async () => {
    respond('<html>Bad gateway</html>', 502)
    await assert.rejects(fetchBundle(spec), {
      message: /could not get a reply from its service/,
    })
  })

  it('does not treat a successful page of another type as a bundle', async () => {
    respond('<html>Sign in</html>', 200, { 'Content-Type': 'text/html' })
    await assert.rejects(fetchBundle(spec), {
      message: /did not send a bundle file/,
    })
  })

  it('reports a timeout, and says nothing was published', async () => {
    globalThis.fetch = (_url, options) =>
      new Promise((_resolve, reject) =>
        options?.signal?.addEventListener('abort', () =>
          reject(new DOMException('aborted', 'TimeoutError')),
        ),
      )
    await assert.rejects(
      fetchBundle(spec, 20),
      (problem) =>
        problem instanceof BundleError &&
        /took too long/.test(problem.failure.message) &&
        /Nothing was published/.test(problem.failure.message),
    )
  })

  it('says the Lab could not be reached when the network fails', async () => {
    globalThis.fetch = async () => {
      throw new TypeError('fetch failed')
    }
    await assert.rejects(fetchBundle(spec), {
      message: /Could not reach the Lab/,
    })
  })
})
