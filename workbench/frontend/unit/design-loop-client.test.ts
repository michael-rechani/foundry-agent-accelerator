import assert from 'node:assert/strict'
import { afterEach, describe, it } from 'node:test'
import {
  asFailure,
  describeChecks,
  designRequest,
  failedRuns,
  lineDiff,
  MAX_ANSWER,
  MAX_FAILED,
  parseCaseDraft,
  parseCaseRun,
  parseRevision,
  pendingJobs,
  regressions,
  rerunScope,
  revisionRequest,
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

  it('keeps each earlier round with the reasons it was revised', () => {
    const file = testFile({
      name: 'Renewal helper',
      templateId: 'document-intake',
      instructions: 'Do the task. State times as written.',
      cases: [test('one')],
      results: { one: [run('one')] },
      rounds: [
        {
          instructions: 'Do the task.',
          changes: ['State times as written.'],
          results: {
            one: [run('one', { passed: false, failures: ['Missing text'] })],
          },
        },
      ],
    })
    assert.equal(file.earlier_rounds.length, 1)
    assert.equal(file.earlier_rounds[0]?.instructions, 'Do the task.')
    assert.deepEqual(file.earlier_rounds[0]?.revised_because, [
      'State times as written.',
    ])
    assert.equal(file.earlier_rounds[0]?.runs[0]?.passed, false)
    assert.deepEqual(
      testFile({
        name: 'x',
        templateId: 'y',
        instructions: 'z',
        cases: [],
        results: {},
      }).earlier_rounds,
      [],
    )
  })
})

describe('failedRuns', () => {
  it('returns the first failing run of each case in case order', () => {
    const cases = [test('one'), test('two'), test('three')]
    const failed = failedRuns(cases, {
      one: [run('one')],
      two: [run('two'), run('two', { passed: false, request_id: 'later' })],
      three: [run('three', { passed: false, request_id: 'first' })],
    })
    assert.deepEqual(
      failed.map((item) => [item.test.id, item.run.request_id]),
      [
        ['two', 'later'],
        ['three', 'first'],
      ],
    )
    assert.deepEqual(failedRuns(cases, {}), [])
  })
})

describe('revisionRequest', () => {
  const failing = (id: string, changes: Partial<CaseRun> = {}) => ({
    test: test(id),
    run: run(id, { passed: false, failures: ['Missing text'], ...changes }),
  })

  it('sends the instructions, the cases and the answers with the cost confirmation', () => {
    const body = revisionRequest({
      instructions: 'Do the task.',
      templateId: 'document-intake',
      failed: [failing('one', { text: 'Nothing changed.' })],
    })
    assert.equal(body.confirm_cost, true)
    assert.equal(body.template_id, 'document-intake')
    assert.equal(body.instructions, 'Do the task.')
    assert.deepEqual(body.failed, [
      {
        case: test('one'),
        text: 'Nothing changed.',
        failures: ['Missing text'],
      },
    ])
  })

  it('bounds how many failures and how much of each answer is sent', () => {
    const many = Array.from({ length: MAX_FAILED + 2 }, (_, index) =>
      failing(`case-${index}`, { text: '😀'.repeat(MAX_ANSWER + 50) }),
    )
    const body = revisionRequest({
      instructions: 'x',
      templateId: 'y',
      failed: many,
    })
    assert.equal(body.failed.length, MAX_FAILED)
    assert.equal([...(body.failed[0]?.text ?? '')].length, MAX_ANSWER)
    assert.doesNotThrow(() => JSON.stringify(body))
  })

  it('never sends an empty list of failures', () => {
    const body = revisionRequest({
      instructions: 'x',
      templateId: 'y',
      failed: [failing('one', { failures: [] })],
    })
    assert.deepEqual(body.failed[0]?.failures, ['Did not pass the checks'])
  })
})

describe('parseRevision', () => {
  const reply = (changes: object = {}) => ({
    instructions: 'Do the task. State times as written.',
    changes: ['State times as written.'],
    usage,
    ...changes,
  })

  it('reads the instructions, the reasons and the usage', () => {
    const revision = parseRevision(reply())
    assert.equal(revision.instructions, 'Do the task. State times as written.')
    assert.deepEqual(revision.changes, ['State times as written.'])
    assert.equal(revision.usage?.total_tokens, 15)
  })

  it('rejects a reply that is not a usable revision', () => {
    for (const bad of [
      null,
      'text',
      reply({ instructions: '   ' }),
      reply({ instructions: 5 }),
      reply({ instructions: 'x'.repeat(6001) }),
      reply({ changes: [] }),
      reply({ changes: 'one' }),
      reply({ changes: ['a', 'b', 'c', 'd', 'e', 'f', 'g'] }),
      reply({ changes: [3] }),
    ])
      assert.throws(() => parseRevision(bad), /revision response is invalid/)
  })
})

describe('rerunScope', () => {
  it('runs every failed case plus a fixed sample of the passes, in case order', () => {
    const cases = ['a', 'b', 'c', 'd', 'e'].map((id) => test(id))
    const scope = rerunScope(cases, {
      a: [run('a')],
      b: [run('b', { passed: false })],
      c: [run('c')],
      d: [run('d')],
      e: [run('e', { passed: false })],
    })
    assert.deepEqual(scope, ['a', 'b', 'c', 'e'])
  })

  it('counts a case with any failing repeat as failed', () => {
    const cases = [test('a'), test('b'), test('c'), test('d')]
    const scope = rerunScope(
      cases,
      {
        a: [run('a'), run('a', { passed: false })],
        b: [run('b')],
        c: [run('c')],
        d: [run('d')],
      },
      1,
    )
    assert.deepEqual(scope, ['a', 'b'])
  })

  it('includes a case that never ran', () => {
    const cases = [test('a'), test('b'), test('c')]
    assert.deepEqual(rerunScope(cases, { a: [run('a')] }, 0), ['b', 'c'])
  })

  it('is empty only when nothing failed and the sample is zero', () => {
    assert.deepEqual(rerunScope([test('a')], { a: [run('a')] }, 0), [])
  })
})

describe('regressions', () => {
  const cases = [test('a'), test('b'), test('c'), test('d')]

  it('names a case that passed every run before and fails one now', () => {
    const before = {
      a: [run('a')],
      b: [run('b'), run('b')],
      c: [run('c', { passed: false })],
      d: [run('d')],
    }
    const after = {
      a: [run('a', { passed: false })],
      b: [run('b'), run('b', { passed: false })],
      c: [run('c', { passed: false })],
      d: [run('d')],
    }
    assert.deepEqual(regressions(cases, before, after), ['a', 'b'])
  })

  it('ignores cases without runs on either side', () => {
    assert.deepEqual(
      regressions(
        cases,
        { a: [run('a')] },
        { b: [run('b', { passed: false })] },
      ),
      [],
    )
  })
})

describe('lineDiff', () => {
  const kinds = (before: string, after: string) =>
    lineDiff(before, after).map((line) => `${line.kind}:${line.text}`)

  it('marks only the lines that changed', () => {
    assert.deepEqual(kinds('one\ntwo\nthree', 'one\nTWO\nthree\nfour'), [
      'same:one',
      'remove:two',
      'add:TWO',
      'same:three',
      'add:four',
    ])
  })

  it('shows an unchanged text as all the same and ignores line ending style', () => {
    assert.deepEqual(kinds('one\r\ntwo', 'one\ntwo'), ['same:one', 'same:two'])
  })

  it('shows a removal and an addition', () => {
    assert.deepEqual(kinds('one\ntwo', 'one'), ['same:one', 'remove:two'])
    assert.deepEqual(kinds('one', 'zero\none'), ['add:zero', 'same:one'])
  })

  it('falls back to remove-all then add-all when the texts are too large to compare', () => {
    const big = Array.from({ length: 1200 }, (_, index) => `line ${index}`)
    const other = big.map((line) => `${line}!`)
    const diff = lineDiff(big.join('\n'), other.join('\n'))
    assert.equal(diff.length, 2400)
    assert.equal(diff[0]?.kind, 'remove')
    assert.equal(diff.at(-1)?.kind, 'add')
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
