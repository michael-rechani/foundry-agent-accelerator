import { expect, test, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import type { Config } from '../src/workspace-config'
import type { CreatedAgent } from '../src/agent-creation-client'
import { demoScenarios } from '../src/demo-scenarios'
import { guidedReview, illustrativeScreenshot } from './fixtures'

const invoice = demoScenarios.find((item) => item.id === 'invoice')!

function invoiceRecord(status: CreatedAgent['status']): CreatedAgent {
  const id = 'created-12345678-1234-4234-9234-123456789abc'
  return {
    id,
    name: 'Fictional invoice helper',
    template_id: invoice.templateId,
    instructions: 'Review fictional invoices using the fixed simulated tools.',
    runtime_name: 'lab-demo-12345678123442349234123456789abc',
    version: '1',
    status,
    stage: status,
    created_at: '2027-04-12T10:00:00Z',
    updated_at: '2027-04-12T10:00:00Z',
    _etag: '"v1"',
    error: null,
    events: [{ name: status, at: '2027-04-12T10:00:00Z' }],
    agent:
      status === 'ready'
        ? {
            ...guidedReview,
            id,
            label: 'Fictional invoice helper',
            agent: 'lab-demo-12345678123442349234123456789abc',
            prompts: [
              { label: 'Try a fictional example', text: invoice.input },
            ],
          }
        : null,
  }
}

async function setup(
  page: Page,
  options: {
    preview?: boolean
    hidden?: boolean
    record?: CreatedAgent
    failedList?: boolean
  } = {},
) {
  const config: Config = {
    title: 'Foundry Agent Lab',
    mode: options.preview ? 'preview' : 'private',
    agents: [
      options.hidden
        ? { ...guidedReview, id: 'custom-unrelated-agent' }
        : guidedReview,
    ],
    default_agent: options.hidden ? 'custom-unrelated-agent' : guidedReview.id,
    max_characters: 60000,
    max_request_bytes: 65536,
    max_history_turns: 10,
    review_timeout_ms: 190000,
    history_timeout_ms: 45000,
    retention_days: 30,
    history_enabled: !options.preview,
    reviews_enabled: !options.preview,
    ...(options.record || options.failedList
      ? {
          agent_creation: {
            enabled: false,
            storage_enabled: true,
            management_enabled: false,
            reason: 'not_enabled',
            requires_operator_key: true as const,
            max_agents: 5,
            publication_timeout_seconds: 600,
          },
        }
      : {}),
  }
  const state = {
    writes: [] as {
      path: string
      body: {
        agent_id: string
        input: string
        history: unknown[]
        thread: string
      }
    }[],
  }
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (request.method() !== 'GET')
      state.writes.push({ path, body: request.postDataJSON() })
    if (path === '/api/config') return route.fulfill({ json: config })
    if (path === '/api/agents')
      return route.fulfill({
        status: options.failedList ? 503 : 200,
        json: options.failedList
          ? { error: 'agents_unavailable' }
          : { items: options.record ? [options.record] : [], cursor: null },
      })
    if (path === '/api/agent-templates')
      return route.fulfill({ json: { draft_mode: 'template', templates: [] } })
    if (path === '/api/review-runs')
      return route.fulfill({ json: { items: [], cursor: null } })
    if (path === '/api/reviews')
      return route.fulfill({
        json: {
          request_id: 'fictional-showcase-response',
          status: 'completed',
          agent: guidedReview.agent,
          text: 'Illustrative test reply: Checklist item 1 has no supplied budget.',
          elapsed_ms: 100,
          receipts: [],
        },
      })
    return route.fulfill({
      status: 404,
      json: { error: 'unexpected_test_request' },
    })
  })
  await page.goto('/#demos')
  await expect(
    page.getByRole('heading', { name: 'From paperwork to a clear next step.' }),
  ).toBeVisible()
  return state
}

test('exploration is read-only and every scenario has an honest customer story', async ({
  page,
}, testInfo) => {
  const state = await setup(page)
  const navigation = page.getByRole('navigation', { name: 'Workspace' })
  await expect(
    navigation.getByRole('button', { name: 'Guided demos' }),
  ).toHaveAttribute('aria-current', 'page')
  for (const scenario of demoScenarios) {
    await page
      .getByRole('navigation', { name: 'Demo scenarios' })
      .getByRole('button', { name: new RegExp(scenario.task) })
      .click()
    await expect(page.locator('.demo-story h2')).toHaveText(scenario.title)
    await expect(page.locator('.demo-story')).toContainText(scenario.decision)
    await expect(
      page.getByText('Illustrative walkthrough, not a live model result'),
    ).toBeVisible()
    await page.locator('.demo-input summary').click()
    await expect(page.locator('.demo-input pre')).toHaveText(scenario.input)
    await page.locator('.demo-input summary').click()
    await page
      .locator('.demo-explorer')
      .evaluate((element) => element.scrollTo({ top: 0 }))
    await page.emulateMedia({ colorScheme: 'light' })
    await illustrativeScreenshot(page, testInfo, `demo-${scenario.id}.png`)
    await page.emulateMedia({ colorScheme: 'dark' })
    await illustrativeScreenshot(page, testInfo, `demo-${scenario.id}-dark.png`)
    expect(state.writes).toEqual([])
  }
  await expect(page.locator('body')).not.toContainText('EXPERIMENTAL')
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true)
})

test('loading a demo preserves unsaved work until confirmed and never auto-sends', async ({
  page,
}) => {
  const state = await setup(page)
  await page.getByRole('button', { name: 'Go straight to Chat' }).click()
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Keep my existing draft')
  await page.getByRole('button', { name: 'Guided demos', exact: true }).click()
  page.once('dialog', (dialog) => dialog.dismiss())
  await page.getByRole('button', { name: 'Load fictional input' }).click()
  await page.getByRole('button', { name: 'Go straight to Chat' }).click()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue('Keep my existing draft')
  await page.getByRole('button', { name: 'Guided demos', exact: true }).click()
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Load fictional input' }).click()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue(demoScenarios[0].input)
  await expect(page.locator('.demo-run-guide')).toContainText(
    'Expected findings, not a live result',
  )
  expect(state.writes).toEqual([])
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => state.writes.length).toBe(1)
  expect(state.writes[0]).toEqual({
    path: '/api/reviews',
    body: {
      agent_id: guidedReview.id,
      input: demoScenarios[0].input,
      history: [],
      thread: expect.stringMatching(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
      ),
    },
  })
})

test('presenter controls keep environment and human-review boundaries visible', async ({
  page,
}, testInfo) => {
  const state = await setup(page)
  const presenter = page.getByRole('button', { name: 'Presenter view' })
  await presenter.click()
  await expect(presenter).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('.chat-app')).toHaveClass(/presenter-view/)
  await page.getByRole('button', { name: 'Load fictional input' }).click()
  await expect(page.locator('.demo-run-guide')).toHaveAttribute('open', '')
  await expect(
    page.getByRole('button', { name: 'Start fresh with this example' }),
  ).toBeVisible()
  await page.locator('.lab-info > summary').click()
  await expect(
    page.getByText('No user sign-in. Saved records are shared.'),
  ).toBeVisible()
  await page.locator('.lab-info > summary').click()
  await illustrativeScreenshot(page, testInfo, 'presenter-view.png')
  page.once('dialog', (dialog) => dialog.accept())
  await page
    .getByRole('button', { name: 'Start fresh with this example' })
    .click()
  expect(state.writes).toEqual([])
  await presenter.click()
  await expect(presenter).toHaveAttribute('aria-pressed', 'false')
})

test('preview and hidden agents never become a simulated live connection', async ({
  page,
}) => {
  const state = await setup(page, { preview: true, hidden: true })
  await expect(page.getByText('Local preview', { exact: true })).toBeVisible()
  await expect(
    page.getByText('Local preview makes no model calls and saves no records.'),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Load fictional input' }),
  ).toHaveCount(0)
  await expect(
    page.getByText('No matching agent is configured.', { exact: false }),
  ).toBeVisible()
  expect(state.writes).toEqual([])
})

for (const status of ['ready', 'failed'] as const) {
  test(`invoice story only uses an explicitly ready created agent (${status})`, async ({
    page,
  }) => {
    const state = await setup(page, { record: invoiceRecord(status) })
    await page
      .getByRole('navigation', { name: 'Demo scenarios' })
      .getByRole('button', { name: /Supplier invoice review/ })
      .click()
    if (status === 'ready') {
      await page.getByRole('button', { name: 'Load fictional input' }).click()
      await expect(page.locator('.agent-picker')).toHaveText(
        'Fictional invoice helper',
      )
      await expect(
        page.getByRole('textbox', { name: 'Message', exact: true }),
      ).toHaveValue(invoice.input)
    } else {
      await expect(
        page.getByRole('button', { name: 'Load fictional input' }),
      ).toHaveCount(0)
      await expect(
        page.getByRole('button', { name: 'Choose Supplier invoice reviewer' }),
      ).toBeVisible()
    }
    expect(state.writes).toEqual([])
  })
}

test('agent storage failures remain explicit while the walkthrough is usable', async ({
  page,
}) => {
  await setup(page, { failedList: true })
  await expect(page.locator('.demo-error')).toContainText(
    'storage is unavailable',
  )
  await expect(page.locator('.demo-story h2')).toHaveText(
    'Find the missing evidence',
  )
})

test('bundled fictional inputs stay aligned with the downloadable demo sources', async () => {
  for (const [id, filename] of [
    ['application', 'application'],
    ['casework', 'casework'],
    ['invoice', 'supplier-invoice'],
  ]) {
    const source = await readFile(
      new URL(`../../../docs/demo-inputs/${filename}.txt`, import.meta.url),
      'utf8',
    )
    expect(demoScenarios.find((item) => item.id === id)!.input).toBe(
      source.replaceAll('\r\n', '\n').trim(),
    )
  }
})
