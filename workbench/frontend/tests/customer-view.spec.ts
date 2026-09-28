import { expect, test, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import type { LibraryTemplate } from '../src/library-catalog'
import type { Config } from '../src/workspace-config'
import { guidedReview } from './fixtures'

const catalog = JSON.parse(
  await readFile(
    new URL('./agent-templates.fixture.json', import.meta.url),
    'utf8',
  ),
)
const grant = (catalog.templates as LibraryTemplate[]).find(
  (item) => item.id === 'grant-reporting-checker',
)!

// Start without the stored switch, as a first-time visitor would.
test.use({ storageState: { cookies: [], origins: [] } })

async function setup(page: Page) {
  const config: Config = {
    title: 'Foundry Agent Lab',
    mode: 'private',
    agents: [guidedReview],
    default_agent: guidedReview.id,
    max_characters: 60000,
    max_request_bytes: 65536,
    max_history_turns: 10,
    review_timeout_ms: 190000,
    history_timeout_ms: 45000,
    retention_days: 30,
    history_enabled: false,
    reviews_enabled: false,
  }
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/config') return route.fulfill({ json: config })
    if (path === '/api/agent-templates') return route.fulfill({ json: catalog })
    return route.fulfill({ json: { error: 'not_found' }, status: 404 })
  })
  await page.goto('/')
  await expect(
    page.getByRole('navigation', { name: 'Workspace' }),
  ).toBeVisible()
}

const navigation = (page: Page) =>
  page.getByRole('navigation', { name: 'Workspace' })
const hoodSwitch = (page: Page) =>
  page.getByRole('switch', { name: /Under the hood/ })

test('the customer view hides technical details until Under the hood is on', async ({
  page,
}) => {
  await setup(page)
  await expect(hoodSwitch(page)).not.toBeChecked()
  await expect(
    page.getByRole('navigation', { name: 'Breadcrumb' }),
  ).toContainText(/Agent library\s*Browse/)
  await expect(navigation(page).locator('.nav-section-label')).toHaveText([
    'Agent library',
    'Try it',
  ])
  await expect(
    navigation(page).getByRole('button', { name: 'Performance' }),
  ).toHaveCount(0)

  await page.locator('.library-card').filter({ hasText: grant.label }).click()
  await expect(
    page.getByRole('heading', { level: 1, name: grant.label, exact: true }),
  ).toBeVisible()
  await expect(page.getByText('Model profile')).toBeHidden()

  await hoodSwitch(page).check()
  await expect(page.getByText('Model profile')).toBeVisible()
  await expect(navigation(page).locator('.nav-section-label')).toHaveText([
    'Agent library',
    'Try it',
    'Measure',
    'Activity',
  ])

  await page.reload()
  await expect(hoodSwitch(page)).toBeChecked()

  await navigation(page).getByRole('button', { name: 'Performance' }).click()
  await expect(
    page.getByRole('navigation', { name: 'Breadcrumb' }),
  ).toContainText(/Measure\s*Performance/)
  await hoodSwitch(page).uncheck()
  await expect(
    navigation(page).getByRole('button', { name: 'All agents' }),
  ).toHaveAttribute('aria-current', 'page')
  await expect(
    navigation(page).getByRole('button', { name: 'Performance' }),
  ).toHaveCount(0)
  expect(
    await page.evaluate(() =>
      localStorage.getItem('ai-foundry-lab-under-the-hood'),
    ),
  ).toBe('0')
})

test('breadcrumbs link back to the library from its tabs', async ({
  page,
}, testInfo) => {
  // Narrow screens show only the current page in the top bar.
  test.skip(testInfo.project.name === 'mobile')
  await setup(page)
  await page
    .getByRole('navigation', { name: 'Agent library' })
    .getByRole('button', { name: 'Guided demos' })
    .click()
  const crumbs = page.getByRole('navigation', { name: 'Breadcrumb' })
  await expect(crumbs).toContainText(/Agent library\s*Guided demos/)
  await crumbs.getByRole('button', { name: 'Agent library' }).click()
  await expect(crumbs).toContainText(/Agent library\s*Browse/)
})
