import { expect, test } from '@playwright/test'
import { support } from './helpers/catalog'
import { openAgent, openLibrary } from './helpers/library-lab'

test('the library says what "My agents" counts next to the agent total', async ({
  page,
}) => {
  await openLibrary(page, { ready: true })
  await expect(page.locator('.library-hero-note')).toContainText(
    'Every agent below can be tried from its own page',
  )
  await expect(page.locator('.library-hero-note')).toContainText('My agents')
})

test('an agent page has no amber review banner and explains its labels on hover', async ({
  page,
}) => {
  await openLibrary(page)
  await openAgent(page, support.label)
  await expect(page.locator('.library-progress')).toHaveCount(0)
  const badges = page.locator('.library-badges .library-badge[title]')
  expect(await badges.count()).toBeGreaterThanOrEqual(3)
  await expect(
    page.getByRole('tab', { name: 'Take it to Foundry' }),
  ).toHaveAttribute('title', /your own Microsoft Foundry project/)
})

test('the catalog uses plain labels instead of Lab jargon', async ({
  page,
}) => {
  await openLibrary(page)
  const main = page.getByRole('main')
  await expect(main).not.toContainText('Focus agent')
  await expect(main).not.toContainText('Sample lookups')
  await expect(
    page.locator('.library-badge', { hasText: 'Featured agent' }).first(),
  ).toBeVisible()
  await expect(
    page.locator('.library-badge', { hasText: 'Looks up sample data' }).first(),
  ).toBeVisible()
})

test('step 3 reads like the other steps until you point at it', async ({
  page,
}) => {
  await openLibrary(page)
  const steps = page.locator('.library-path li')
  const link = page.locator('.library-path-link')
  await expect(link).toHaveText('Make your own copy')
  const [linkStyle, plainStyle] = await Promise.all([
    link.evaluate((node) => {
      const style = getComputedStyle(node)
      return { color: style.color, decoration: style.textDecorationLine }
    }),
    steps.first().evaluate((node) => {
      const style = getComputedStyle(node)
      return { color: style.color, decoration: style.textDecorationLine }
    }),
  ])
  expect(linkStyle).toEqual(plainStyle)
})

test('an open agent page labels its own tabs apart from the library tabs', async ({
  page,
}) => {
  await openLibrary(page)
  const library = page.getByRole('navigation', { name: 'Agent library' })
  await openAgent(page, support.label)
  await expect(library).toBeVisible()
  await expect(page.locator('.library-tabs-label')).toHaveText(
    `More about ${support.label}`,
  )
  await expect(
    page.getByRole('tablist', { name: 'Agent details' }),
  ).toBeVisible()
})
