import { expect, test } from '@playwright/test'

const labPolicy =
  "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"

test('the design sketch runs under the Lab security policy', async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, 'The sketch is desktop-only; mobile is tracked in #65.')
  const violations: string[] = []
  page.on('console', (message) => {
    if (/Content Security Policy/i.test(message.text()))
      violations.push(message.text())
  })
  await page.route('**/ideas/**', async (route) => {
    const response = await route.fetch()
    await route.fulfill({
      response,
      headers: {
        ...response.headers(),
        'content-security-policy': labPolicy,
      },
    })
  })
  await page.goto('/ideas/')
  await expect(page.getByText('not the working Lab')).toBeVisible()
  await expect(page.locator('body')).toHaveClass(/dark/)
  await expect(page.getByRole('button', { name: /Traces/ })).toBeHidden()
  await page.getByRole('button', { name: 'Under the hood' }).last().click()
  await expect(page.getByRole('button', { name: /Traces/ })).toBeVisible()
  await page.getByRole('button', { name: /Scorecards/ }).click()
  await expect(page.getByRole('heading', { name: /Scorecard/ })).toBeVisible()
  await expect(
    page.getByRole('link', { name: 'Back to the Lab' }),
  ).toHaveAttribute('href', '/')
  expect(violations).toEqual([])
})
