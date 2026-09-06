import { expect, test, type Page } from '@playwright/test'
import type { Review } from '../src/ReviewWorkspace'

async function setup(page: Page, preview = false) {
  const state = {
    document: null as Review | null,
    executions: 0,
    conflict: false,
    pollFailure: null as 'network' | 'rate-limit' | null,
    runningReads: 0,
  }
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/config')
      return route.fulfill({
        json: {
          title: 'AI Foundry Lab',
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
          agents: [
            {
              id: 'customer-review',
              label: 'Customer review',
              category: 'Coordinator',
              description: 'Evidence review',
              agent: 'customer-review-coordinator',
              tools: {},
              prompts: [],
            },
          ],
        },
      })
    if (path === '/api/review-runs' && request.method() === 'POST') {
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
    const document = state.document
    if (!document)
      return route.fulfill({ status: 404, json: { error: 'not_found' } })
    if (path.endsWith('/execute')) {
      if (state.conflict)
        return route.fulfill({ status: 409, json: { error: 'review_changed' } })
      expect(request.headers()['if-match']).toBe(document._etag)
      state.executions++
      document.status = 'running'
      document._etag = String(Number(document._etag) + 1)
      document.runs.push({
        id: 'run-' + state.executions,
        started_at: document.updated_at,
        input: {
          criteria: [...document.criteria],
          evidence: structuredClone(document.evidence),
        },
        events: [{ name: 'review_started', at: document.updated_at }],
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
  await page.goto('/')
  await expect(page.locator('.agent-picker')).toContainText('Customer review')
  const navigation = page.getByRole('navigation', { name: 'Workspace' })
  await expect(navigation.getByRole('button').first()).toHaveText('Chat')
  await expect(navigation.getByRole('button', { name: 'Chat', exact: true })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toBeVisible()
  await navigation.getByRole('button', { name: 'Evidence reviews', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Evidence reviews', exact: true }),
  ).toBeVisible()
  return state
}

test('navigation is labelled and conversation actions stay in Chat', async ({ page }, testInfo) => {
  await setup(page, true)
  await expect(page.locator('body')).not.toContainText(/preview/i)
  await expect(page.getByRole('heading', { name: 'Review storage unavailable' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save to shared history' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Export conversation' })).toHaveCount(0)
  await expect(page.locator('.sidebar-session')).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath('reviews-navigation.png') })
  const navigation = page.getByRole('navigation', { name: 'Workspace' })
  for (const label of ['Chat', 'Evidence reviews', 'Shared history', 'Agent catalog', 'Performance']) {
    await expect(navigation.locator('span').filter({ hasText: new RegExp(`^${label}$`) })).toBeVisible()
  }
  for (const label of ['Chat', 'Agent catalog', 'Performance']) {
    await navigation.getByRole('button', { name: label, exact: label !== 'Agent catalog' }).click()
    await expect(page.locator('body')).not.toContainText(/preview/i)
    await expect(page.getByRole('button', { name: 'Export conversation' })).toHaveCount(label === 'Chat' ? 1 : 0)
    await page.screenshot({ path: testInfo.outputPath(`${label.toLowerCase().replaceAll(' ', '-')}.png`) })
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

async function create(page: Page) {
  await page.getByRole('button', { name: 'New review', exact: true }).click()
  await page.getByRole('button', { name: 'Use synthetic example' }).click()
  await page.getByRole('button', { name: 'Create review' }).click()
  await expect(
    page.getByRole('button', { name: 'Run review', exact: true }),
  ).toBeVisible()
}

test('review, inspect evidence, clarify, resume, reopen and preserve snapshots', async ({
  page,
}, testInfo) => {
  const state = await setup(page)
  await create(page)
  await page.getByRole('button', { name: 'Run review', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Evidence requested' }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'SRC-1' }).click()
  await expect(
    page.getByRole('complementary', { name: 'Source evidence' }),
  ).toContainText('Twelve weekly workshops')
  await page.getByRole('tab', { name: 'Findings' }).click()
  await page.screenshot({
    path: testInfo.outputPath('review-findings.png'),
    fullPage: true,
  })
  await page.getByLabel('Additional evidence').fill('Budget: $100.')
  await page.getByRole('button', { name: 'Save evidence' }).click()
  await page.getByRole('tab', { name: 'Evidence', exact: true }).click()
  await page.getByLabel('Evidence source').selectOption('SRC-2')
  await expect(
    page.getByRole('complementary', { name: 'Source evidence' }),
  ).toContainText('Budget: $100.')
  await page.getByRole('button', { name: 'Resume review' }).click()
  await expect(page.getByText('Review complete', { exact: true })).toBeVisible()
  await page.reload()
  await expect(
    page.getByRole('heading', { name: 'Community workshop application' }),
  ).toBeVisible()
  await page.getByLabel('Run version').selectOption({ value: '0' })
  await page.getByRole('tab', { name: 'Evidence', exact: true }).click()
  await expect(
    page.getByLabel('Evidence source').locator('option'),
  ).toHaveCount(1)
  await page.getByLabel('Run version').selectOption({ value: '1' })
  await expect(
    page.getByLabel('Evidence source').locator('option'),
  ).toHaveCount(2)
  await page.getByRole('tab', { name: 'Activity' }).click()
  await expect(
    page.getByText('Source references and exact quotes checked'),
  ).toBeVisible()
  expect(state.executions).toBe(2)
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
})

for (const failure of ['network', 'rate-limit'] as const) {
  test(`refresh restarts polling after ${failure} without another execution`, async ({ page }) => {
    const state = await setup(page)
    await create(page)
    state.pollFailure = failure
    state.runningReads = 1
    await page.getByRole('button', { name: 'Run review', exact: true }).click()
    await expect(page.getByRole('alert')).toBeVisible()
    await page.getByRole('button', { name: 'Refresh reviews' }).click()
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Evidence requested' })).toBeVisible()
    expect(state.executions).toBe(1)
    expect(state.runningReads).toBe(0)
  })
}

test('inbox counts reflect loaded records and status filters', async ({ page }, testInfo) => {
  const state = await setup(page)
  await expect(page.getByRole('heading', { name: 'No reviews yet' })).toBeVisible()
  await expect(page.locator('.review-overview dd')).toHaveText(['0', '0', '0', '0'])
  await create(page)
  await page.getByRole('button', { name: 'Run review', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Evidence requested' })).toBeVisible()
  await page.getByRole('button', { name: 'Back to reviews' }).click()
  await expect(page.locator('.overview-all dd')).toHaveText('1')
  await expect(page.locator('.overview-waiting_input dd')).toHaveText('1')
  await expect(page.locator('.overview-running dd')).toHaveText('0')
  await expect(page.locator('.overview-completed dd')).toHaveText('0')
  await page.getByLabel('Review status', { exact: true }).selectOption('completed')
  await expect(page.getByRole('heading', { name: 'No matching reviews' })).toBeVisible()
  await page.getByLabel('Review status', { exact: true }).selectOption('waiting_input')
  await expect(page.locator('.review-row')).toHaveCount(1)
  await expect(page.locator('.review-row')).toContainText(state.document!.title)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(await page.evaluate(() => document.getAnimations().filter((animation) => animation.playState === 'running').length)).toBe(0)
  await page.screenshot({ path: testInfo.outputPath('review-inbox.png'), fullPage: true })
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
  await page.getByRole('button', { name: 'Use synthetic example' }).click()
  await expect(
    page.getByRole('button', { name: 'Create review' }),
  ).toBeDisabled()
  await expect(page.getByLabel('Review title')).toHaveValue(
    'Community workshop application',
  )
  await page.screenshot({
    path: testInfo.outputPath('review-draft.png'),
    fullPage: true,
  })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
})
