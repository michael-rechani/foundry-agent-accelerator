import { expect, test, type Page } from '@playwright/test'
import type { Review } from '../src/review-client'
import type { Agent } from '../src/workspace-config'
import { guidedReview, illustrativeScreenshot, registry } from './fixtures'

async function setup(
  page: Page,
  preview = false,
  agents: Agent[] = [guidedReview],
) {
  const state = {
    document: null as Review | null,
    executions: 0,
    recoveries: 0,
    conflict: false,
    pollFailure: null as 'network' | 'rate-limit' | null,
    runningReads: 0,
    chatRequests: 0,
    creations: [] as Pick<
      Review,
      'title' | 'agent_id' | 'criteria' | 'evidence'
    >[],
  }
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/config')
      return route.fulfill({
        json: {
          title: 'Foundry Agent Lab',
          mode: preview ? 'preview' : 'private',
          reviews_enabled: !preview,
          history_enabled: !preview,
          default_agent: 'customer-review',
          retention_days: 30,
          max_characters: 60000,
          max_request_bytes: 65536,
          max_history_turns: 10,
          review_timeout_ms: 190000,
          history_timeout_ms: 45000,
          agents,
        },
      })
    if (path === '/api/review-runs' && request.method() === 'POST') {
      state.creations.push(request.postDataJSON())
      state.document = {
        ...request.postDataJSON(),
        id: 'review-12345678-1234-1234-1234-123456789abc',
        status: 'draft',
        runs: [],
        _etag: '1',
        updated_at: '2026-09-06T00:00:00Z',
      }
      return route.fulfill({ status: 201, json: state.document })
    }
    if (path === '/api/review-runs')
      return route.fulfill({
        json: { items: state.document ? [state.document] : [], cursor: null },
      })
    if (path === '/api/reviews') {
      state.chatRequests++
      return route.fulfill({
        status: 400,
        json: { error: 'unexpected_chat_request' },
      })
    }
    const document = state.document
    if (!document)
      return route.fulfill({ status: 404, json: { error: 'not_found' } })
    if (path.endsWith('/execute') || path.endsWith('/resume')) {
      const recovering = path.endsWith('/resume')
      if (state.conflict)
        return route.fulfill({ status: 409, json: { error: 'review_changed' } })
      expect(request.headers()['if-match']).toBe(document._etag)
      const previous = document.runs.at(-1)
      if (recovering) {
        expect(request.postDataJSON()).toEqual({ confirm_cost: true })
        expect(document.status).toBe('interrupted')
        expect(document.runs.length).toBeLessThan(4)
        state.recoveries++
      }
      state.executions++
      document.status = 'running'
      document._etag = String(Number(document._etag) + 1)
      document.runs.push({
        id: 'run-' + state.executions,
        started_at: document.updated_at,
        input: recovering
          ? structuredClone(previous!.input)
          : {
              criteria: [...document.criteria],
              evidence: structuredClone(document.evidence),
            },
        events: [
          {
            name: recovering ? 'review_recovery_requested' : 'review_started',
            at: document.updated_at,
          },
        ],
        ...(recovering ? { resumed_from: previous!.id } : {}),
      })
      return route.fulfill({ status: 202, json: document })
    }
    if (path.endsWith('/evidence')) {
      expect(request.headers()['if-match']).toBe(document._etag)
      document.evidence.push(request.postDataJSON())
      document.status = 'draft'
      document._etag = String(Number(document._etag) + 1)
      return route.fulfill({ json: document })
    }
    if (document.status === 'running') {
      if (state.pollFailure) {
        const failure = state.pollFailure
        state.pollFailure = null
        return failure === 'network'
          ? route.abort('failed')
          : route.fulfill({ status: 429, json: { error: 'reviews_busy' } })
      }
      if (state.runningReads > 0) {
        state.runningReads--
        return route.fulfill({ json: document })
      }
      document.status = state.executions === 1 ? 'waiting_input' : 'completed'
      const run = document.runs.at(-1)!
      run.elapsed_ms = 1234
      run.result = {
        summary: 'Application evidence reviewed.',
        findings: [
          {
            criterion_id: 'CRIT-1',
            assessment: state.executions === 1 ? 'gap' : 'supported',
            explanation:
              state.executions === 1
                ? 'Budget is missing.'
                : 'Budget supplied.',
            citations:
              state.executions === 1
                ? []
                : [{ source_id: 'SRC-2', quote: 'Budget: $100.' }],
          },
          {
            criterion_id: 'CRIT-2',
            assessment: 'supported',
            explanation: 'A delivery timeline is stated.',
            citations: [
              {
                source_id: 'SRC-1',
                quote: 'Twelve weekly workshops beginning October 1.',
              },
            ],
          },
        ],
        questions:
          state.executions === 1 ? ['What is the project budget?'] : [],
      }
      run.events.push(
        { name: 'citations_checked', at: document.updated_at },
        { name: document.status, at: document.updated_at },
      )
      document._etag = String(Number(document._etag) + 1)
    }
    return route.fulfill({ json: document })
  })
  await page.goto('/#chat')
  await expect(page.locator('.agent-picker')).toContainText(
    'Application and case helper',
  )
  const navigation = page.getByRole('navigation', { name: 'Workspace' })
  await expect(navigation.getByRole('button').first()).toHaveText('Chat')
  await expect(
    navigation.getByRole('button', { name: 'Chat', exact: true }),
  ).toHaveAttribute('aria-current', 'page')
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toBeVisible()
  await expect(
    navigation.getByRole('button', { name: 'Document reviews' }),
  ).toHaveCount(0)
  if (preview) {
    await expect(page.locator('.chat-review-link')).toHaveCount(0)
    await page.goto('/#reviews')
    await page.reload()
  } else
    await page
      .locator('.chat-review-link')
      .getByRole('button', { name: 'Document reviews', exact: true })
      .click()
  await expect(
    navigation.getByRole('button', { name: 'Document reviews', exact: true }),
  ).toHaveAttribute('aria-current', 'page')
  await expect(
    page.getByRole('heading', { name: 'Document reviews', exact: true }),
  ).toBeVisible()
  return state
}

test('navigation is labelled and conversation actions stay in Chat', async ({
  page,
}, testInfo) => {
  await setup(page, true)
  await expect(page.getByText('Local preview', { exact: true })).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'Review storage unavailable' }),
  ).toBeVisible()
  await expect(page.locator('.review-scope')).toContainText(
    'Check the text you paste against your own checklist',
  )
  await expect(page.locator('.review-intro')).toContainText(
    'Your Chat messages are not copied here, and review results are not sent back to Chat',
  )
  await expect(page.locator('.review-steps li')).toHaveText([
    'Add a checklist and document text',
    'Run a review',
    'Read results beside the original text',
    'Add missing information and review again',
  ])
  await expect(
    page.getByRole('complementary', { name: 'Lab data boundary' }),
  ).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: 'Save to shared history' }),
  ).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: 'Export conversation' }),
  ).toHaveCount(0)
  await illustrativeScreenshot(page, testInfo, 'reviews-navigation.png')
  const navigation = page.getByRole('navigation', { name: 'Workspace' })
  for (const label of [
    'Chat',
    'Document reviews',
    'Shared history',
    'All agents',
    'Performance',
  ]) {
    await expect(
      navigation.locator('span').filter({ hasText: new RegExp(`^${label}$`) }),
    ).toBeVisible()
  }
  for (const label of ['Chat', 'All agents', 'Performance']) {
    await navigation.getByRole('button', { name: label, exact: true }).click()
    await expect(page.getByText('Local preview', { exact: true })).toBeVisible()
    await expect(
      page.getByRole('button', { name: 'Export conversation' }),
    ).toHaveCount(label === 'Chat' ? 1 : 0)
    await page.screenshot({
      path: testInfo.outputPath(
        `${label.toLowerCase().replaceAll(' ', '-')}.png`,
      ),
    })
  }
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
})

test('review guide explains findings, storage and human decision boundaries', async ({
  page,
}) => {
  const state = await setup(page)
  const guide = page.locator('.review-guide')
  await guide.locator('summary').click()
  await expect(guide.locator('dt')).toHaveText(['Supported', 'Gap', 'Conflict'])
  await expect(guide).toContainText('does not prove the text is true')
  await expect(guide).toContainText('does not mean the application has failed')
  await expect(guide).toContainText('Statements disagree')
  await expect(guide).toContainText('not whether it is true')
  await expect(guide).toContainText(
    'a copy of its input, results, follow-up questions and records of tool calls',
  )
  await expect(guide).toContainText(
    'Anyone who can open this Lab can read saved reviews and add requested information',
  )
  await expect(guide).toContainText('Records are not private to you')
  await expect(guide).toContainText('30 days after their last update')
  await expect(guide).toContainText(
    'cannot delete a review or edit its saved checklist',
  )
  await expect(guide).toContainText('not a continuation of Chat')
  await expect(guide).toContainText(
    'Requirements and proposal review is in preview',
  )
  expect(state.executions).toBe(0)
  expect(state.creations).toHaveLength(0)
})

test('document reviews use the Lab default and do not transfer Chat drafts', async ({
  page,
}, testInfo) => {
  const caseAgent = registry.find((item) => item.id === 'case-review')!
  const state = await setup(page, false, [guidedReview, caseAgent])
  const navigation = page.getByRole('navigation', { name: 'Workspace' })
  await navigation.getByRole('button', { name: 'All agents' }).click()
  await page
    .getByRole('navigation', { name: 'Agent library' })
    .getByRole('button', { name: /^Ready to use/ })
    .click()
  await page
    .locator('.catalog-agent')
    .filter({
      has: page.getByRole('heading', { name: caseAgent.label, exact: true }),
    })
    .getByRole('button', { name: 'Start chat' })
    .click()
  const editor = page.getByRole('textbox', { name: 'Message', exact: true })
  await editor.fill('Fictional case notes only for Chat, not review evidence')
  await page
    .locator('.chat-review-link')
    .getByRole('button', { name: 'Document reviews', exact: true })
    .click()
  await page.getByRole('button', { name: 'New review', exact: true }).click()
  await expect(page.getByLabel('Review title')).toHaveValue('')
  await expect(page.getByLabel('Checklist, one item per line')).toHaveValue('')
  await expect(page.getByLabel('Document 1', { exact: true })).toHaveValue('')
  await expect(page.locator('.review-form-bar')).toContainText(
    'Agent doing this check: Application and case helper',
  )
  await expect(page.locator('.review-form-bar')).toContainText(
    "Uses the Lab's default agent, not your Chat selection",
  )
  await page.getByRole('button', { name: 'Use fictional example' }).click()
  expect(state.creations).toHaveLength(0)
  await expect(page.locator('#review-privacy')).toBeVisible()
  await expect(page.locator('#review-privacy')).toContainText(
    'never personal or confidential information',
  )
  await expect(page.locator('#review-privacy')).toContainText(
    'Reviews expire 30 days after the last update; backup retention is separate.',
  )
  await expect(
    page.getByRole('button', { name: 'Create shared review' }),
  ).toHaveAttribute('aria-describedby', 'review-privacy')
  await page
    .getByRole('button', { name: 'Create shared review' })
    .scrollIntoViewIfNeeded()
  await expect(page.locator('#review-privacy')).toBeInViewport({ ratio: 0.99 })
  await expect(
    page.getByRole('button', { name: 'Create shared review' }),
  ).toBeInViewport({ ratio: 1 })
  await illustrativeScreenshot(page, testInfo, 'review-privacy.png', 'sidebar')
  await page.emulateMedia({ colorScheme: 'dark' })
  await illustrativeScreenshot(
    page,
    testInfo,
    'review-privacy-dark.png',
    'sidebar',
  )
  await page.emulateMedia({ colorScheme: 'light' })
  await page.getByRole('button', { name: 'Create shared review' }).click()
  await expect(
    page.getByRole('button', { name: 'Run review', exact: true }),
  ).toBeVisible()
  expect(state.creations).toHaveLength(1)
  expect(state.creations[0].agent_id).toBe('customer-review')
  expect(Object.keys(state.creations[0]).sort()).toEqual([
    'agent_id',
    'criteria',
    'evidence',
    'title',
  ])
  expect(JSON.stringify(state.creations[0])).not.toContain('only for Chat')
  expect(state.executions).toBe(0)
  expect(state.chatRequests).toBe(0)
  await navigation.getByRole('button', { name: 'Chat', exact: true }).click()
  await expect(page.locator('.agent-picker')).toHaveText(caseAgent.label)
  await expect(editor).toHaveValue(
    'Fictional case notes only for Chat, not review evidence',
  )
})

test('invalid review links fall back to the library without opening a review', async ({
  page,
}) => {
  await setup(page)
  await page.goto('/#review-not-a-valid-id')
  await page.reload()
  await expect(
    page
      .getByRole('navigation', { name: 'Workspace' })
      .getByRole('button', { name: 'All agents', exact: true }),
  ).toHaveAttribute('aria-current', 'page')
  await expect(
    page.getByRole('heading', { level: 1, name: /library|job that needs/i }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'Document reviews', exact: true }),
  ).toHaveCount(0)
})

async function create(page: Page) {
  await page.getByRole('button', { name: 'New review', exact: true }).click()
  await page.getByRole('button', { name: 'Use fictional example' }).click()
  await page.getByRole('button', { name: 'Create shared review' }).click()
  await expect(
    page.getByRole('button', { name: 'Run review', exact: true }),
  ).toBeVisible()
}

async function interrupt(page: Page) {
  const state = await setup(page)
  await create(page)
  state.runningReads = 100
  await page.getByRole('button', { name: 'Run review', exact: true }).click()
  await expect(page.getByText('Running', { exact: true })).toBeVisible()
  state.document!.status = 'interrupted'
  state.document!.runs[0].error = 'execution_interrupted'
  state.document!.runs[0].events.push({
    name: 'interrupted',
    at: state.document!.updated_at,
  })
  state.document!._etag = '3'
  await page.reload()
  await expect(
    page.getByRole('button', { name: 'Recover review' }),
  ).toBeVisible()
  return state
}

test('interrupted recovery requires consent, uses saved input and preserves history', async ({
  page,
}, testInfo) => {
  const state = await interrupt(page)
  const original = structuredClone(state.document!.runs[0])
  await expect(page.locator('.review-next-step')).toContainText(
    'recovery may incur another model charge',
  )
  await page.getByRole('button', { name: 'Refresh reviews' }).click()
  expect(state.recoveries).toBe(0)
  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('may incur another model charge')
    await dialog.dismiss()
  })
  await page.getByRole('button', { name: 'Recover review' }).click()
  expect(state.executions).toBe(1)
  expect(state.document!.runs).toEqual([original])
  await page.screenshot({
    path: testInfo.outputPath('review-recovery.png'),
    fullPage: true,
  })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Recover review' }).click()
  await expect(page.getByText('Running', { exact: true })).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Recover review' }),
  ).toHaveCount(0)
  expect(state.recoveries).toBe(1)
  expect(state.document!.runs[0]).toEqual(original)
  expect(state.document!.runs[1].input).toEqual(original.input)
  expect(state.document!.runs[1].resumed_from).toBe(original.id)
  state.runningReads = 0
  await expect(page.getByText('Results saved', { exact: true })).toBeVisible()
  await page.reload()
  await page.getByRole('tab', { name: 'Run details' }).click()
  await expect(
    page.getByText('Recovery requested using saved input'),
  ).toBeVisible()
  await page.getByLabel('Run version').selectOption('0')
  await expect(page.getByText('Run error: execution_interrupted')).toBeVisible()
  expect(state.executions).toBe(2)
})

test('recovery conflicts preserve input and never silently resubmit', async ({
  page,
}) => {
  const state = await interrupt(page)
  const original = structuredClone(state.document)
  state.conflict = true
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Recover review' }).click()
  await expect(
    page.getByRole('alert').filter({ hasText: 'This review changed' }),
  ).toBeVisible()
  expect(state.document).toEqual(original)
  await page.getByRole('button', { name: 'Refresh reviews' }).click()
  expect(state.recoveries).toBe(0)
  expect(state.executions).toBe(1)
})

test('recovery is unavailable after the four-run limit or a saved failure', async ({
  page,
}) => {
  const state = await interrupt(page)
  state.document!.runs = Array.from({ length: 4 }, (_, index) => ({
    ...structuredClone(state.document!.runs[0]),
    id: `run-${index + 1}`,
  }))
  await page.getByRole('button', { name: 'Refresh reviews' }).click()
  await expect(page.locator('.review-next-step')).toContainText(
    'four-run limit has been reached',
  )
  await expect(
    page.getByRole('button', { name: 'Recover review' }),
  ).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: 'Export review' }),
  ).toBeEnabled()
  state.document!.status = 'failed'
  state.document!.runs = state.document!.runs.slice(0, 1)
  await page.getByRole('button', { name: 'Refresh reviews' }).click()
  await expect(
    page.getByRole('button', { name: 'Recover review' }),
  ).toHaveCount(0)
  expect(state.recoveries).toBe(0)
})

test('review, inspect evidence, clarify, resume, reopen and preserve snapshots', async ({
  page,
}, testInfo) => {
  const state = await setup(page)
  await create(page)
  await expect(page.locator('.review-next-step')).toContainText(
    'Checklist and documents saved; no results yet',
  )
  expect(state.executions).toBe(0)
  await page.getByRole('button', { name: 'Run review', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'More information needed' }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Document 1' }).click()
  await expect(
    page.getByRole('complementary', { name: 'Original text' }),
  ).toContainText('Twelve weekly workshops')
  await page.getByRole('tab', { name: 'Results' }).click()
  await expect(page.locator('.review-disclaimer')).toContainText(
    'they do not prove those documents are true',
  )
  await expect(page.locator('.review-disclaimer')).toContainText(
    'They do not approve applications or make business decisions',
  )
  await illustrativeScreenshot(page, testInfo, 'review-findings.png')
  await page.emulateMedia({ colorScheme: 'dark' })
  await illustrativeScreenshot(page, testInfo, 'review-findings-dark.png')
  await page.emulateMedia({ colorScheme: 'light' })
  await page
    .getByLabel('More information', { exact: true })
    .fill('Budget: $100.')
  await page.getByRole('button', { name: 'Save added information' }).click()
  expect(state.executions).toBe(1)
  await expect(page.locator('.review-next-step')).toContainText(
    'saved but not checked yet',
  )
  await page.getByRole('tab', { name: 'Original text', exact: true }).click()
  await page.getByLabel('Document', { exact: true }).selectOption('SRC-2')
  await expect(
    page.getByRole('complementary', { name: 'Original text' }),
  ).toContainText('Budget: $100.')
  await page.getByRole('button', { name: 'Review again' }).click()
  await expect(page.getByText('Results saved', { exact: true })).toBeVisible()
  await page.reload()
  await expect(
    page
      .getByRole('navigation', { name: 'Workspace' })
      .getByRole('button', { name: 'Document reviews', exact: true }),
  ).toHaveAttribute('aria-current', 'page')
  await expect(
    page.getByRole('heading', { name: 'Community workshop application' }),
  ).toBeVisible()
  await page.getByLabel('Run version').selectOption({ value: '0' })
  await page.getByRole('tab', { name: 'Original text', exact: true }).click()
  await expect(
    page.getByLabel('Document', { exact: true }).locator('option'),
  ).toHaveCount(1)
  await page.getByLabel('Run version').selectOption({ value: '1' })
  await expect(
    page.getByLabel('Document', { exact: true }).locator('option'),
  ).toHaveCount(2)
  await page.getByRole('tab', { name: 'Run details' }).click()
  await expect(page.getByText('Quotes matched to your documents')).toBeVisible()
  expect(state.executions).toBe(2)
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
})

for (const failure of ['network', 'rate-limit'] as const) {
  test(`refresh restarts polling after ${failure} without another execution`, async ({
    page,
  }) => {
    const state = await setup(page)
    await create(page)
    state.pollFailure = failure
    state.runningReads = 1
    await page.getByRole('button', { name: 'Run review', exact: true }).click()
    await expect(page.getByRole('alert')).toBeVisible()
    await page.getByRole('button', { name: 'Refresh reviews' }).click()
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(
      page.getByRole('heading', { name: 'More information needed' }),
    ).toBeVisible()
    expect(state.executions).toBe(1)
    expect(state.runningReads).toBe(0)
  })
}

test('inbox counts reflect loaded records and status filters', async ({
  page,
}, testInfo) => {
  const state = await setup(page)
  await expect(
    page.getByRole('heading', { name: 'No reviews yet' }),
  ).toBeVisible()
  await expect(page.locator('.review-overview dd')).toHaveText([
    '0',
    '0',
    '0',
    '0',
  ])
  await create(page)
  await page.getByRole('button', { name: 'Run review', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'More information needed' }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Back to reviews' }).click()
  await expect(page.locator('.overview-all dd')).toHaveText('1')
  await expect(page.locator('.overview-waiting_input dd')).toHaveText('1')
  await expect(page.locator('.overview-running dd')).toHaveText('0')
  await expect(page.locator('.overview-completed dd')).toHaveText('0')
  await page
    .getByLabel('Review status', { exact: true })
    .selectOption('completed')
  await expect(
    page.getByRole('heading', { name: 'No matching reviews' }),
  ).toBeVisible()
  await page
    .getByLabel('Review status', { exact: true })
    .selectOption('waiting_input')
  await expect(page.locator('.review-row')).toHaveCount(1)
  await expect(page.locator('.review-row')).toContainText(state.document!.title)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  expect(
    await page.evaluate(
      () =>
        document
          .getAnimations()
          .filter((animation) => animation.playState === 'running').length,
    ),
  ).toBe(0)
  await page.screenshot({
    path: testInfo.outputPath('review-inbox.png'),
    fullPage: true,
  })
})

test('conflict preserves review and never silently resubmits', async ({
  page,
}) => {
  const state = await setup(page)
  await create(page)
  state.conflict = true
  await page.getByRole('button', { name: 'Run review', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('This review changed')
  expect(state.executions).toBe(0)
})

test('preview accepts a synthetic draft but never executes', async ({
  page,
}, testInfo) => {
  await setup(page, true)
  await page.getByRole('button', { name: 'New review', exact: true }).click()
  await page.getByRole('button', { name: 'Use fictional example' }).click()
  await expect(
    page.getByRole('button', { name: 'Create shared review' }),
  ).toBeDisabled()
  await expect(page.getByLabel('Review title')).toHaveValue(
    'Community workshop application',
  )
  await illustrativeScreenshot(page, testInfo, 'review-draft.png')
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
})
