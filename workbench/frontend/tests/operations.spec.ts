import { expect, test } from '@playwright/test'
import { screenshot } from './fixtures'
import {
  healthy,
  labStatus,
  openOverview,
  openWorkspace,
  serviceStatus,
} from './helpers/chat-lab'
import { workspaceNav } from './helpers/navigation'

test('Operations Overview shows service health, when it was checked and re-checks on request', async ({
  page,
}, testInfo) => {
  await page.clock.install()
  const state = await openWorkspace(page)
  const nav = workspaceNav(page)
  expect(state.healthRequests).toBe(0)
  await openOverview(page)
  for (const service of ['Lab', 'Foundry connection', 'History store'])
    await expect(serviceStatus(page, service)).toHaveText('Ready')
  await expect(labStatus(page)).toHaveText('Ready')
  await expect(page.locator('.operations-actions .micro-label')).toHaveText(
    /^Status as of \d{1,2}:\d{2}/,
  )
  await expect(
    page.getByText(
      'The Lab re-checks itself every minute, so this can be up to a minute behind.',
    ),
  ).toBeVisible()
  await screenshot(page, testInfo, 'operations-overview.png')
  expect(state.healthRequests).toBe(1)

  // Coming back inside the minute re-uses the last answer.
  await nav.getByRole('button', { name: 'Performance', exact: true }).click()
  await openOverview(page)
  await expect(serviceStatus(page, 'Foundry connection')).toHaveText('Ready')

  const refresh = page.getByRole('button', { name: 'Refresh', exact: true })
  await refresh.click()
  await expect.poll(() => state.healthRequests).toBe(2)
  await expect(refresh).toBeEnabled()
  expect(state.healthRequests).toBe(2)

  // Opening it again after a minute asks again.
  await page.clock.runFor(61_000)
  await nav.getByRole('button', { name: 'Performance', exact: true }).click()
  await openOverview(page)
  await expect.poll(() => state.healthRequests).toBe(3)
})

for (const item of [
  {
    name: 'a service needs attention',
    options: {
      health: {
        status: 503,
        body: { status: 'degraded', foundry: 'unavailable', cosmos: 'ready' },
      },
    },
    overall: 'Needs attention',
    foundry: 'Needs attention',
    history: 'Ready',
  },
  {
    name: 'the Lab is still starting',
    options: { health: { status: 503, body: { status: 'starting' } } },
    overall: 'Starting',
    foundry: 'Starting',
    history: 'Starting',
  },
  {
    name: 'a preview has no live connections',
    options: {
      preview: true,
      health: { status: 503, body: { status: 'disabled' } },
    },
    overall: 'Preview only',
    foundry: 'Off',
    history: 'Off',
  },
  {
    name: 'the answer cannot be read',
    options: { health: { status: 502, html: true } },
    overall: "Couldn't check",
    foundry: "Couldn't check",
    history: "Couldn't check",
  },
] satisfies {
  name: string
  options: Parameters<typeof openWorkspace>[1]
  overall: string
  foundry: string
  history: string
}[])
  test(`Operations Overview says so when ${item.name}`, async ({ page }) => {
    await openWorkspace(page, item.options)
    await openOverview(page)
    await expect(labStatus(page)).toHaveText(item.overall)
    await expect(serviceStatus(page, 'Lab')).toHaveText('Ready')
    await expect(serviceStatus(page, 'Foundry connection')).toHaveText(
      item.foundry,
    )
    await expect(serviceStatus(page, 'History store')).toHaveText(item.history)
  })

test('Refresh on Operations Overview recovers after a failed check', async ({
  page,
}) => {
  const state = await openWorkspace(page, {
    health: [{ status: 502, html: true }, healthy],
  })
  await openOverview(page)
  await expect(serviceStatus(page, 'Foundry connection')).toHaveText(
    "Couldn't check",
  )
  await page.getByRole('button', { name: 'Refresh', exact: true }).click()
  await expect(serviceStatus(page, 'Foundry connection')).toHaveText('Ready')
  await expect(labStatus(page)).toHaveText('Ready')
  expect(state.healthRequests).toBe(2)
})

test('preview calls do not count as live performance', async ({ page }) => {
  await openWorkspace(page, { preview: true })
  await page
    .getByRole('textbox', { name: 'Message' })
    .fill('Synthetic preview request')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.getByRole('alert')).toContainText('No agent was invoked')
  await page.getByRole('button', { name: 'Performance', exact: true }).click()
  await expect(page.locator('.metric-strip > div').first()).toContainText('0')
})

test('replies show reported tokens and Performance estimates cost from user rates', async ({
  page,
}) => {
  const state = await openWorkspace(page, {
    usage: {
      input_tokens: 1200,
      output_tokens: 300,
      total_tokens: 1500,
      cached_tokens: 200,
      reasoning_tokens: 120,
    },
  })
  await page.evaluate(() => localStorage.removeItem('foundry-lab-token-rates'))
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Review the fictional application')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.assistant-heading')).toContainText(
    '1.0s · 1,500 tokens',
  )
  await page.locator('.receipt-details > summary').click()
  await expect(page.locator('.usage-detail')).toContainText(
    '1,200 in (200 cached) · 300 out (120 reasoning) · 1,500 total',
  )
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect.poll(() => state.saves.length).toBe(1)
  expect(state.saves[0].turns[0].result.usage?.total_tokens).toBe(1500)

  const nav = workspaceNav(page)
  await nav.getByRole('button', { name: /^Request log/ }).click()
  await expect(
    page.getByRole('table', { name: 'Request log' }).locator('tbody td').nth(4),
  ).toHaveText('1,500 tokens')
  await nav.getByRole('button', { name: 'Performance', exact: true }).click()
  const cost = page.getByRole('region', { name: 'Token usage and cost' })
  await expect(cost.locator('.metric-strip > div')).toHaveText([
    /Input tokens\s*1,200/,
    /Output tokens\s*300/,
    /Estimated cost\s*Add your rates/,
  ])
  await cost.getByLabel('Input rate per 1M tokens').fill('2')
  await cost.getByLabel('Output rate per 1M tokens').fill('8')
  await cost.getByRole('button', { name: 'Use rates' }).click()
  // 1,200 x 2 / 1M + 300 x 8 / 1M
  await expect(cost.locator('.metric-strip > div').nth(2)).toContainText(
    '0.0048',
  )
  await page.reload()
  await nav.getByRole('button', { name: 'Performance', exact: true }).click()
  await expect(cost.getByLabel('Input rate per 1M tokens')).toHaveValue('2')
  await cost.getByRole('button', { name: 'Clear' }).click()
  expect(
    await page.evaluate(() => localStorage.getItem('foundry-lab-token-rates')),
  ).toBeNull()
  await expect(cost.locator('#budget-alert-status')).toContainText(
    'budget alerts aren’t set up for this Lab',
  )
})

test('Performance says when an Azure budget alerts on Lab spend', async ({
  page,
}) => {
  await openWorkspace(page, { config: { budget_alerts: true } })
  await workspaceNav(page)
    .getByRole('button', { name: 'Performance', exact: true })
    .click()
  const status = page.locator('#budget-alert-status')
  await expect(status).toContainText('50%, 80% and 100%')
  await expect(status).not.toContainText('aren’t set up')
})

test('replies without reported tokens say so instead of showing zero', async ({
  page,
}) => {
  await openWorkspace(page, { usage: null })
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Review the fictional application')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.assistant-heading')).toContainText(
    'Tokens not reported',
  )
  await workspaceNav(page)
    .getByRole('button', { name: 'Performance', exact: true })
    .click()
  await expect(
    page.getByRole('region', { name: 'Token usage and cost' }),
  ).toContainText('1 did not report tokens and are not counted')
})
