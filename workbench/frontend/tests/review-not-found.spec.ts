import { expect, test, type Page } from '@playwright/test'
import { guidedReview } from './fixtures'

const unknownReview = '#review-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'
const notFoundMessage =
  'That review could not be found. It may have been removed, or the link may be wrong.'

async function mockLab(
  page: Page,
  missing: { status: number; body: string; contentType: string },
) {
  const lookups: string[] = []
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/config')
      return route.fulfill({
        json: {
          title: 'Foundry Agent Lab',
          mode: 'private',
          reviews_enabled: true,
          history_enabled: true,
          default_agent: 'customer-review',
          retention_days: 30,
          max_characters: 60000,
          max_request_bytes: 65536,
          max_history_turns: 10,
          review_timeout_ms: 190000,
          history_timeout_ms: 45000,
          agents: [guidedReview],
        },
      })
    if (path === '/api/review-runs')
      return route.fulfill({ json: { items: [], cursor: null } })
    if (path.startsWith('/api/review-runs/')) {
      lookups.push(path)
      return route.fulfill(missing)
    }
    return route.fulfill({ status: 404, json: { error: 'not_found' } })
  })
  return lookups
}

const notFound = {
  status: 404,
  body: '{"error": "not_found"}',
  contentType: 'application/json',
}

test('a review link to a review that does not exist says so in plain words', async ({
  page,
}) => {
  const lookups = await mockLab(page, notFound)
  await page.goto('/' + unknownReview)

  const notice = page.getByRole('alert').filter({ hasText: notFoundMessage })
  await expect(notice).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'Document reviews', exact: true }),
  ).toBeVisible()
  expect(lookups).toEqual(['/api/review-runs/' + unknownReview.slice(1)])
  await expect(
    page.getByText('The request could not be confirmed'),
  ).toHaveCount(0)
})

test('a review link followed after the Lab has loaded says so in plain words', async ({
  page,
}) => {
  await mockLab(page, notFound)
  await page.goto('/#reviews')
  await expect(
    page.getByRole('heading', { name: 'Document reviews', exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)

  await page.evaluate((link) => {
    window.location.hash = link
  }, unknownReview)

  await expect(
    page.getByRole('alert').filter({ hasText: notFoundMessage }),
  ).toBeVisible()
})

test('a gateway page in place of a review shows a plain message, not a parse error', async ({
  page,
}) => {
  await mockLab(page, {
    status: 502,
    body: '<html><body>502 Bad Gateway</body></html>',
    contentType: 'text/html',
  })
  await page.goto('/' + unknownReview)

  const notice = page.getByRole('alert').filter({
    hasText: 'The request could not be confirmed.',
  })
  await expect(notice).toBeVisible()
  await expect(notice).not.toContainText(/JSON|Unexpected token/i)
})
