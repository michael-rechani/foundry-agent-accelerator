import { type Page, expect, test } from '@playwright/test'
import { labConfig } from './helpers/lab-config'
import { mockApi } from './helpers/mock-api'
import { followLink } from './helpers/navigation'

const unknownReview = '#review-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'
const notFoundMessage =
  'That review could not be found. It may have been removed, or the link may be wrong.'

async function mockLab(
  page: Page,
  missing: { status: number; body: string; contentType: string },
) {
  const lookups: string[] = []
  await mockApi(page, async ({ route, path, respond }) => {
    if (path === '/api/config')
      return respond(
        labConfig({ reviews_enabled: true, history_enabled: true }),
      )
    if (path === '/api/review-runs') return respond({ items: [], cursor: null })
    if (path.startsWith('/api/review-runs/')) {
      lookups.push(path)
      return route.fulfill(missing)
    }
    return respond({ error: 'not_found' }, 404)
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

  await followLink(page, unknownReview)

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
