import { type Page, expect, test } from '@playwright/test'
import { guidedReview } from './fixtures'
import {
  catalog,
  invoice,
  scorecards,
  scorecardsWithout,
  support,
  templateById,
} from './helpers/catalog'
import { foundryPortal, labConfig } from './helpers/lab-config'
import { mockApi } from './helpers/mock-api'
import {
  hoodSwitch,
  libraryNav,
  waitForLab,
  workspaceNav,
} from './helpers/navigation'
import { type Config } from '../src/workspace-config'

// Start without the stored switch, as a first-time visitor would.
test.use({ storageState: { cookies: [], origins: [] } })

async function openCustomerView(
  page: Page,
  overrides: Partial<Config> = {},
  withoutResultsFor?: string,
  results = scorecards,
) {
  const config = labConfig({ reviews_enabled: false, ...overrides })
  const served = scorecardsWithout(withoutResultsFor, results)
  await mockApi(page, ({ path, respond }) => {
    if (path === '/api/config') return respond(config)
    if (path === '/api/agent-templates') return respond(catalog)
    if (path === '/api/agent-scorecards') return respond(served)
    return respond({ error: 'not_found' }, 404)
  })
  await page.goto('/')
  await waitForLab(page)
}

test('the customer view hides technical details until Under the hood is on', async ({
  page,
}) => {
  await openCustomerView(page)
  await expect(hoodSwitch(page)).not.toBeChecked()
  await expect(
    page.getByRole('navigation', { name: 'Breadcrumb' }),
  ).toContainText(/Agent library\s*Browse/)
  await expect(workspaceNav(page).locator('.nav-section-label')).toHaveText([
    'Agent library',
    'Try it',
  ])
  for (const name of ['Overview', 'Performance'])
    await expect(workspaceNav(page).getByRole('button', { name })).toHaveCount(
      0,
    )

  await page.locator('.library-card').filter({ hasText: support.label }).click()
  await expect(
    page.getByRole('heading', { level: 1, name: support.label, exact: true }),
  ).toBeVisible()
  await expect(page.getByText('Model profile')).toBeHidden()

  await hoodSwitch(page).check()
  await expect(page.getByText('Model profile')).toBeVisible()
  await expect(workspaceNav(page).locator('.nav-section-label')).toHaveText([
    'Agent library',
    'Try it',
    'Operations',
  ])
  await expect(
    workspaceNav(page)
      .getByRole('group', { name: 'Operations' })
      .getByRole('button'),
  ).toHaveText(['Overview', 'Performance', /^Request log/])

  await page.reload()
  await expect(hoodSwitch(page)).toBeChecked()

  await workspaceNav(page).getByRole('button', { name: 'Performance' }).click()
  await expect(
    page.getByRole('navigation', { name: 'Breadcrumb' }),
  ).toContainText(/Operations\s*Performance/)
  await hoodSwitch(page).uncheck()
  await expect(
    workspaceNav(page).getByRole('button', { name: /^All agents/ }),
  ).toHaveAttribute('aria-current', 'page')
  await expect(
    workspaceNav(page).getByRole('button', { name: 'Performance' }),
  ).toHaveCount(0)
  expect(
    await page.evaluate(() =>
      localStorage.getItem('ai-foundry-lab-under-the-hood'),
    ),
  ).toBe('0')
})

test('add-on technical details stay hidden until Under the hood is on', async ({
  page,
}) => {
  await openCustomerView(page)
  await libraryNav(page).getByRole('button', { name: 'Add-ons' }).click()
  const first = page.locator('.addon-card').first()
  await expect(first).toContainText('Knowledge search')
  await expect(first).toContainText('What it would cost')
  await expect(first.getByText('Azure AI Search')).toBeHidden()
  await expect(first.getByText('Add-ons roadmap (#54)')).toBeHidden()
  await expect(
    first.getByRole('button', { name: /Copy request for your coding agent/ }),
  ).toBeHidden()

  await hoodSwitch(page).check()
  await expect(first.getByText('Azure AI Search')).toBeVisible()
  await expect(first.getByText('Add-ons roadmap (#54)')).toBeVisible()
  await expect(
    first.getByRole('button', { name: /Copy request for your coding agent/ }),
  ).toBeVisible()
})

test('Foundry links appear only under the hood', async ({ page }) => {
  await openCustomerView(page, { foundry_portal: foundryPortal })
  const projectLink = page.getByRole('link', {
    name: /Open project in Foundry/,
  })
  await expect(projectLink).toHaveCount(0)

  await hoodSwitch(page).check()
  await expect(projectLink).toHaveAttribute('href', foundryPortal)
  await expect(projectLink).toHaveAttribute('target', '_blank')
  await expect(projectLink).toHaveAttribute('rel', 'noopener noreferrer')

  await workspaceNav(page).getByRole('button', { name: 'Performance' }).click()
  await expect(page.locator('.foundry-note').getByRole('link')).toHaveAttribute(
    'href',
    foundryPortal,
  )
  await workspaceNav(page)
    .getByRole('button', { name: /^Request log/ })
    .click()
  await expect(page.locator('.foundry-note').getByRole('link')).toHaveAttribute(
    'href',
    foundryPortal,
  )

  await workspaceNav(page).getByRole('button', { name: 'Chat' }).click()
  await expect(page.locator('.chat-aside')).toHaveCount(0)
  await page.locator('.agent-about > summary').click()
  const runtime = page.locator('.agent-about .catalog-runtime')
  await runtime.getByText('Developer setup details').click()
  await expect(runtime.getByRole('link').first()).toHaveAttribute(
    'href',
    `${foundryPortal}/build/agents/${guidedReview.agent}/build`,
  )
  await expect(runtime.getByRole('link')).toHaveCount(
    1 + Object.keys(guidedReview.tools).length,
  )

  await hoodSwitch(page).uncheck()
  await expect(page.getByRole('link', { name: /Foundry/ })).toHaveCount(0)
})

test('breadcrumbs link back to the library from its tabs', async ({
  page,
}, testInfo) => {
  // Narrow screens show only the current page in the top bar.
  test.skip(testInfo.project.name === 'mobile')
  await openCustomerView(page)
  await libraryNav(page).getByRole('button', { name: 'Guided demos' }).click()
  const crumbs = page.getByRole('navigation', { name: 'Breadcrumb' })
  await expect(crumbs).toContainText(/Agent library\s*Guided demos/)
  await crumbs.getByRole('button', { name: 'Agent library' }).click()
  await expect(crumbs).toContainText(/Agent library\s*Browse/)
})

test('an agent page leads with plain actions and keeps setup details under the hood', async ({
  page,
}) => {
  await openCustomerView(page)
  await expect(page.locator('.library-card').first()).toContainText(
    invoice.label,
  )
  await page.locator('.library-card').filter({ hasText: invoice.label }).click()
  const detail = page.locator('.library-detail')
  await expect(
    detail.getByRole('button', { name: 'Try it with an example' }),
  ).toBeVisible()
  await expect(
    detail.getByRole('button', { name: 'Take it to Foundry' }),
  ).toBeVisible()
  await expect(detail).not.toContainText(/fictional|made[- ]up/i)
  await expect(page.getByText('Before you use it')).toBeHidden()
  await expect(detail.locator('.library-tools code').first()).toBeHidden()
  await expect(detail.locator('.library-tools')).toContainText(
    invoice.tools[0].description,
  )

  await detail.getByRole('button', { name: 'Try it with an example' }).click()
  await expect(page.getByRole('tab', { name: 'Try it' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  await expect(page.getByRole('tabpanel')).toContainText(invoice.sample_input)
})

test('test results read plainly and keep case details under the hood', async ({
  page,
}) => {
  // Every recorded answer may pass, so give one agent an answer that needs a look and shows notes.
  const withMiss = structuredClone(scorecards)
  const card = withMiss.scorecards[0]
  card.cases[0].passed = false
  card.cases[0].runs_passed = card.cases[0].runs - 1
  card.cases[0].notes = ["Run 3: missing 'item 1'"]
  card.summary.passed = card.cases.filter(
    (entry: { passed: boolean }) => entry.passed,
  ).length
  card.summary.runs_passed = card.cases.reduce(
    (total: number, entry: { runs_passed: number }) =>
      total + entry.runs_passed,
    0,
  )
  const benefits = templateById(card.template_id)
  const {
    passed,
    runs,
    runs_passed: runsPassed,
    runs_per_case: each,
  } = card.summary
  await openCustomerView(page, {}, undefined, withMiss)
  await page
    .locator('.library-card')
    .filter({ hasText: benefits.label })
    .click()
  await page.getByRole('tab', { name: 'Test results' }).click()
  const panel = page.getByRole('tabpanel')
  expect(
    await page
      .getByRole('tablist', { name: 'Agent details' })
      .evaluate((list) => list.scrollWidth <= list.clientWidth),
  ).toBe(true)
  await expect(panel.getByRole('heading', { level: 2 })).toHaveText(
    'How it did on its test cases',
  )
  await expect(panel).toContainText('September 29, 2026')
  await expect(panel).toContainText(
    `a sample request ${each} times and checks every answer`,
  )
  await expect(panel).toContainText(
    `${5 - passed} of 5 test ${5 - passed === 1 ? 'case has' : 'cases have'} an answer that missed a check`,
  )
  await expect(panel.locator('.scorecard-facts > div')).toHaveText([
    new RegExp(`Answer checks\\s*${runsPassed} of ${runs} answers passed`),
    /Typical response\s*\d+\.\d s/,
    /Model cost per answer\s*(Under 1?|About \d+?)/,
    /Sign-off\s*Waiting for a person/,
  ])
  const cases = panel
    .getByRole('list', { name: 'Test cases' })
    .locator(':scope > li')
  await expect(cases).toHaveCount(5)
  await expect(cases.filter({ hasText: /Passed/ })).toHaveCount(passed)
  await expect(cases.filter({ hasText: 'Needs a look' })).toHaveCount(
    5 - passed,
  )
  await expect(cases.first()).toContainText(card.cases[0].goal)
  await expect(cases.first()).toContainText(
    `${card.cases[0].runs_passed} of ${card.cases[0].runs} answers passed`,
  )
  // The ring and dots only draw the counts the sentences already state.
  await expect(panel.locator('.scorecard-ring')).toHaveAttribute(
    'data-state',
    'some',
  )
  const missed = cases.first().locator('.scorecard-dots')
  await expect(missed.locator('.pass')).toHaveCount(card.cases[0].runs_passed)
  await expect(missed.locator('.miss')).toHaveCount(1)
  await expect(panel).not.toContainText(/fictional|made[- ]up/i)
  await expect(panel.locator('.scorecard-case-detail').first()).toBeHidden()
  await expect(panel.locator('.scorecard-notes').first()).toBeHidden()

  await hoodSwitch(page).check()
  await expect(panel.locator('.scorecard-case-detail').first()).toContainText(
    card.cases[0].id,
  )
  await expect(panel.locator('.scorecard-notes').first()).toBeVisible()
  await expect(panel).toContainText(`Model ${card.model}.`)
  await hoodSwitch(page).uncheck()
})

test('a ring and one dot per answer repeat the written counts without adding words', async ({
  page,
}) => {
  const card = scorecards.scorecards[0]
  const agent = templateById(card.template_id)
  await openCustomerView(page)
  await page.locator('.library-card').filter({ hasText: agent.label }).click()
  await page.getByRole('tab', { name: 'Test results' }).click()
  const panel = page.getByRole('tabpanel')
  await expect(panel).toContainText(
    `${card.summary.runs_passed} of ${card.summary.runs} answers passed`,
  )
  const ring = panel.locator('.scorecard-ring')
  await expect(ring).toHaveCount(1)
  await expect(ring).toHaveAttribute('aria-hidden', 'true')
  await expect(ring).toHaveAttribute(
    'data-state',
    card.summary.runs_passed === card.summary.runs ? 'all' : 'some',
  )
  await expect(ring).toHaveText('')
  const rows = panel
    .getByRole('list', { name: 'Test cases' })
    .locator(':scope > li')
  await expect(rows).toHaveCount(card.cases.length)
  for (const [index, entry] of card.cases.entries()) {
    await expect(rows.nth(index)).toContainText(entry.goal)
    const dots = rows.nth(index).locator('.scorecard-dots')
    await expect(dots).toHaveAttribute('aria-hidden', 'true')
    await expect(dots.locator('span')).toHaveCount(entry.runs)
    await expect(dots.locator('.pass')).toHaveCount(entry.runs_passed)
    await expect(dots.locator('.miss')).toHaveCount(
      entry.runs - entry.runs_passed,
    )
  }
})

test('agents without a recorded run say so on Test results', async ({
  page,
}) => {
  await openCustomerView(page, {}, support.id)
  await page.locator('.library-card').filter({ hasText: support.label }).click()
  await page.getByRole('tab', { name: 'Test results' }).click()
  await expect(page.getByRole('tabpanel')).toContainText('No test results yet')
})
