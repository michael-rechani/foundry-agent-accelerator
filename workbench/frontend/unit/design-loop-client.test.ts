import assert from 'node:assert/strict'
import { afterEach, describe, it } from 'node:test'
import {
  asFailure,
  describeChecks,
  designRequest,
  parseCaseDraft,
  parseCaseRun,
  pendingJobs,
  summarizeRuns,
  testFile,
  testFileName,
  TestRequestError,
  type CaseRun,
  type TestCase,
} from '../src/design-loop-client.ts'

const originalFetch = globalThis.fetch

afterEach(() => {
  globalThis.fetch = originalFetch
})

const test = (id: string, changes: Partial<TestCase> = {}): TestCase => ({
  id,
  category: 'grounded',
  input: 'Sample notice: hours change to 8:00 on Monday.',
  checks: { must_include: ['8:00'] },
  rubric: 'States the new hours.',
  ...changes,
})

const run = (id: string, changes: Partial<CaseRun> = {}): CaseRun => ({
  request_id: `request-${id}`,
  case_id: id,
  passed: true,
  failures: [],
  text: 'The hours change to 8:00.',
  receipts: [],
  elapsed_ms: 900,
  usage: null,
  ...changes,
})

const usage = {
  input_tokens: 10,
  output_tokens: 5,
  total_tokens: 15,
  cached_tokens: null,
  reasoning_tokens: null,
}

describe('parseCaseDraft', () => {
  const body = (cases: unknown[], extra: object = {}) => ({
    cases,
    rejected: [],
    elapsed_ms: 10,
    usage,
    ...extra,
  })

  it('reads the cases, the dropped count and the reported tokens', () => {
    const draft = parseCaseDraft(
      body([test('one'), test('two')], {
        rejected: [{ id: 'x', problems: [] }],
      }),
    )
    assert.deepEqual(
      draft.cases.map((item) => item.id),
      ['one', 'two'],
    )
    assert.equal(draft.dropped, 1)
    assert.equal(draft.usage?.total_tokens, 15)
  })

  it('keeps the check shapes the Lab accepts', () => {
    const checks = {
      must_include: ['a'],
      must_include_any: [['b', 'c']],
      guards: ['no_approval'],
      asks_question: true,
      expected_tools: ['lookup_demo_request'],
    }
    assert.deepEqual(
      parseCaseDraft(body([test('one', { checks })])).cases[0].checks,
      checks,
    )
  })

  it('refuses a reply that is not a list of well-formed cases', () => {
    for (const bad of [
      null,
      {},
      body([]),
      body(['text']),
      body([{ ...test('one'), rubric: 3 }]),
      body([test('one', { checks: { must_include: [1] } as never })]),
      body([test('one', { checks: { asks_question: 'yes' } as never })]),
      body([test('one', { checks: null as never })]),
      body([test('one'), test('one')]),
    ])
      assert.throws(() => parseCaseDraft(bad), {
        message: 'The test case response is invalid.',
      })
  })
})

describe('parseCaseRun', () => {
  const body = (changes: object = {}) => ({
    request_id: 'request-1',
    case_id: 'one',
    passed: false,
    failures: ["missing '8:00'"],
    text: 'No idea.',
    receipts: [
      {
        tool: 'lookup_demo_request',
        call_id: 'c1',
        verified: true,
        agent: null,
        output: '{}',
      },
    ],
    elapsed_ms: 1200,
    usage,
    ...changes,
  })

  it('reads a run with its failures, receipts and tokens', () => {
    const parsed = parseCaseRun(body())
    assert.equal(parsed.passed, false)
    assert.deepEqual(parsed.failures, ["missing '8:00'"])
    assert.equal(parsed.receipts[0].tool, 'lookup_demo_request')
    assert.equal(parsed.usage?.total_tokens, 15)
  })

  it('treats absent tokens as not reported', () => {
    assert.equal(parseCaseRun(body({ usage: null })).usage, null)
  })

  it('refuses a malformed run', () => {
    for (const bad of [
      null,
      body({ passed: 'yes' }),
      body({ failures: 'none' }),
      body({ text: undefined }),
      body({ receipts: [{ tool: 1 }] }),
      body({ elapsed_ms: '12' }),
    ])
      assert.throws(() => parseCaseRun(bad), {
        message: 'The test result is invalid.',
      })
  })
})

describe('pendingJobs', () => {
  const cases = [test('one'), test('two')]

  it('lists every case once, then every case again for each repeat', () => {
    assert.deepEqual(
      pendingJobs(cases, {}, 2).map((job) => `${job.test.id}:${job.repeat}`),
      ['one:0', 'two:0', 'one:1', 'two:1'],
    )
  })

  it('skips runs that already came back, so a stopped run can continue', () => {
    const results = { one: [run('one')] }
    assert.deepEqual(
      pendingJobs(cases, results, 2).map(
        (job) => `${job.test.id}:${job.repeat}`,
      ),
      ['two:0', 'one:1', 'two:1'],
    )
  })

  it('has nothing left once every repeat is in', () => {
    const results = { one: [run('one')], two: [run('two')] }
    assert.deepEqual(pendingJobs(cases, results, 1), [])
  })
})

describe('summarizeRuns', () => {
  it('counts runs and passes across the current cases only', () => {
    const results = {
      one: [run('one'), run('one', { passed: false })],
      gone: [run('gone')],
    }
    assert.deepEqual(summarizeRuns([test('one')], results), {
      runs: 2,
      passed: 1,
    })
  })
})

describe('describeChecks', () => {
  it('turns each check into a short plain line', () => {
    assert.deepEqual(
      describeChecks({
        must_include: ['8:00', 'Monday'],
        must_include_any: [['ask', 'confirm']],
        guards: ['no_approval'],
        asks_question: true,
        expected_tools: ['lookup_demo_request'],
      }),
      [
        'Mentions "8:00", "Monday"',
        'Mentions one of "ask" or "confirm"',
        'Never no approval',
        'Asks a question',
        'Calls lookup_demo_request',
      ],
    )
  })

  it('says nothing for an empty check set', () => {
    assert.deepEqual(describeChecks({}), [])
  })
})

describe('testFile', () => {
  it('keeps the cases and each answer, and says a pass is not proof', () => {
    const file = testFile({
      name: 'Renewal helper',
      templateId: 'document-intake',
      instructions: 'Do the task.',
      cases: [test('one')],
      results: {
        one: [
          run('one', {
            receipts: [
              {
                tool: 'lookup_demo_request',
                call_id: null,
                verified: false,
                agent: null,
                output: null,
              },
            ],
          }),
        ],
      },
    })
    assert.match(file.note, /person must read each answer/)
    assert.equal(file.template_id, 'document-intake')
    assert.deepEqual(file.runs, [
      {
        case_id: 'one',
        passed: true,
        failures: [],
        answer: 'The hours change to 8:00.',
        tools_called: ['lookup_demo_request'],
        elapsed_ms: 900,
      },
    ])
  })

  it('names the file after the spec', () => {
    assert.equal(
      testFileName({ name: 'Renewal Checklist Helper' }),
      'renewal-checklist-helper.test-cases.json',
    )
  })
})

describe('designRequest', () => {
  function respond(body: string, status: number, headers: HeadersInit = {}) {
    globalThis.fetch = async () => new Response(body, { status, headers })
  }

  it('posts JSON with the Lab header and returns the parsed body', async () => {
    let received: RequestInit | undefined
    let url = ''
    globalThis.fetch = async (input, options) => {
      url = String(input)
      received = options
      return new Response('{"cases":[]}')
    }
    const data = await designRequest('agent-test-cases', { a: 1 }, 1000)
    const headers = received?.headers as Record<string, string>
    assert.deepEqual(data, { cases: [] })
    assert.equal(url, '/api/agent-test-cases')
    assert.equal(received?.method, 'POST')
    assert.equal(received?.body, '{"a":1}')
    assert.equal(headers['X-Workbench-Request'], '1')
    assert.equal(headers['Content-Type'], 'application/json')
  })

  it('explains an unusable case draft without blaming the setup', async () => {
    respond('{"error":"cases_unusable","request_id":"r-1"}', 502)
    await assert.rejects(
      designRequest('agent-test-cases', {}, 1000),
      (problem) =>
        problem instanceof TestRequestError &&
        /did not return usable test cases/.test(problem.failure.message) &&
        problem.failure.reference === 'r-1',
    )
  })

  it('asks the person to wait when the Lab is busy, with no countdown', async () => {
    respond('{"error":"busy"}', 429, { 'Retry-After': '45' })
    await assert.rejects(
      designRequest('agent-test-runs', {}, 1000),
      (problem) =>
        problem instanceof TestRequestError &&
        problem.failure.retryAfter === undefined &&
        /Wait a minute, then try again/.test(problem.failure.message),
    )
  })

  it('uses the shared message for codes the chat already explains', async () => {
    respond('{"error":"library_preview_disabled"}', 503)
    await assert.rejects(designRequest('agent-test-runs', {}, 1000), {
      message: /Library previews are turned off/,
    })
  })

  it('reports a timeout as a timeout, not as a stop', async () => {
    globalThis.fetch = (_url, options) =>
      new Promise((_resolve, reject) =>
        options?.signal?.addEventListener('abort', () =>
          reject(new DOMException('aborted', 'AbortError')),
        ),
      )
    await assert.rejects(
      designRequest('agent-test-runs', {}, 20),
      (problem) =>
        problem instanceof TestRequestError &&
        /timed out/.test(problem.failure.message),
    )
  })

  it('rethrows the abort when the person stops the work', async () => {
    globalThis.fetch = (_url, options) =>
      new Promise((_resolve, reject) =>
        options?.signal?.addEventListener('abort', () =>
          reject(new DOMException('aborted', 'AbortError')),
        ),
      )
    const stop = new AbortController()
    const pending = designRequest('agent-test-runs', {}, 5000, stop.signal)
    stop.abort()
    await assert.rejects(pending, { name: 'AbortError' })
  })

  it('says the Lab could not be reached when the network fails', async () => {
    globalThis.fetch = async () => {
      throw new TypeError('fetch failed')
    }
    await assert.rejects(designRequest('agent-test-runs', {}, 1000), {
      message: /Could not reach the Lab/,
    })
  })
})

describe('asFailure', () => {
  it('passes a request failure through and wraps other problems', () => {
    const request = new TestRequestError(asFailure(new Error('Plain problem')))
    assert.equal(asFailure(request).message, 'Plain problem')
    assert.equal(asFailure(new Error('Other')).message, 'Other')
  })
})
