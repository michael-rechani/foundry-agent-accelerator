import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'

const catalog = JSON.parse(
  await readFile(
    new URL('./agent-templates.fixture.json', import.meta.url),
    'utf8',
  ),
)

const labPolicy =
  "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"

test('the preview runs under the Lab security policy', async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, 'The preview is desktop-only; mobile is tracked in #65.')
  const violations: string[] = []
  page.on('console', (message) => {
    if (/Content Security Policy/i.test(message.text()))
      violations.push(message.text())
  })
  await page.route('**/preview/**', async (route) => {
    const response = await route.fetch()
    await route.fulfill({
      response,
      headers: {
        ...response.headers(),
        'content-security-policy': labPolicy,
      },
    })
  })
  await page.route('**/api/agent-templates', (route) => route.abort())
  await page.goto('/preview/')
  await expect(page.getByTestId('preview-badge')).toHaveText('Preview')
  await expect(page.locator('body')).toHaveClass(/dark/)
  await expect(
    page.getByRole('heading', { name: 'Agent library' }),
  ).toBeVisible()
  await expect(page.locator('#cards .card')).toHaveCount(
    catalog.templates.length,
  )
  await expect(page.locator('body')).not.toContainText(
    /made[- ]up|fictional|contoso|sketch/i,
  )

  await page.getByRole('button', { name: 'Reviewed', exact: true }).click()
  await expect(page.locator('#cards .card')).toHaveCount(9)
  await page.getByLabel('Search agents').last().fill('invoice')
  await page
    .getByRole('button', { name: 'Try Supplier invoice reviewer' })
    .click()
  await expect(page.getByRole('heading', { name: 'Playground' })).toBeVisible()
  await expect(
    page.getByText(/Doesn't match: the documents support/),
  ).toBeVisible()

  await expect(page.getByRole('button', { name: /Traces/ })).toBeHidden()
  await page.getByRole('switch', { name: 'Under the hood' }).click()
  await expect(page.getByRole('button', { name: /Traces/ })).toBeVisible()
  await expect(page.getByLabel('Trace', { exact: true })).toBeVisible()
  await page
    .getByRole('button', { name: /Scorecard/ })
    .first()
    .click()
  await expect(page.getByRole('heading', { name: 'Scorecard' })).toBeVisible()
  await expect(page.getByText('5 of 5')).toBeVisible()

  await page.getByRole('button', { name: 'Switch to light theme' }).click()
  await expect(page.locator('body')).not.toHaveClass(/dark/)
  await expect(
    page.getByRole('link', { name: 'Back to the Lab' }),
  ).toHaveAttribute('href', '/')
  expect(violations).toEqual([])
})

test('the bundled library snapshot matches the catalog', async () => {
  const source = await readFile(
    new URL('../public/preview/preview-data.js', import.meta.url),
    'utf8',
  )
  const sandbox: { PREVIEW_AGENTS?: unknown } = {}
  new Function('window', source)(sandbox)
  const snapshot = sandbox.PREVIEW_AGENTS
  expect(snapshot).toEqual(
    catalog.templates.map((template: Record<string, any>) => ({
      id: template.id,
      label: template.label,
      summary: template.summary,
      readiness: template.readiness.id,
      readinessLabel: template.readiness.label,
      toolMode: template.tool_mode.label,
      sector: template.sector.label,
      industry: template.industry.label,
      decides: template.human_decision,
      output: template.output,
    })),
  )
})

test('the preview prefers the live catalog', async ({ page, isMobile }) => {
  test.skip(isMobile, 'The preview is desktop-only; mobile is tracked in #65.')
  const templates = catalog.templates.slice(0, 3)
  await page.route('**/api/agent-templates', (route) =>
    route.fulfill({ json: { ...catalog, templates } }),
  )
  await page.goto('/preview/')
  await expect(page.locator('#cards .card')).toHaveCount(3)
  await expect(page.getByText('3 agents')).toBeVisible()
})
