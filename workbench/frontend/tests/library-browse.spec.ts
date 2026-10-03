import { expect, test } from '@playwright/test'
import { screenshot } from './fixtures'
import { catalog, support, templates } from './helpers/catalog'
import { expectFitsViewport } from './helpers/layout'
import { openLibrary } from './helpers/library-lab'
import { workspaceNav } from './helpers/navigation'

test('browse, filter and search the catalog with live counts', async ({
  page,
}, testInfo) => {
  await openLibrary(page)
  const results = page.getByRole('heading', { level: 2, name: /agents?$/ })
  const cards = page.locator('.library-card')
  await expect(results).toHaveText(`${templates.length} agents`)
  await expect(cards).toHaveCount(templates.length)
  await expect(page.locator('.library-filters legend')).toHaveText([
    'Sector and industry',
    'Task',
    'Readiness',
    'Works with',
  ])
  const publicCount = templates.filter(
    (item) => item.sector.id === 'public',
  ).length
  const facet = (name: string) =>
    page
      .locator('.library-facet')
      .filter({ has: page.getByText(name, { exact: true }) })
  await expect(facet('Healthcare and public sector')).toContainText(
    String(publicCount),
  )
  await facet('Healthcare and public sector').click()
  await expect(facet('Healthcare and public sector')).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await expect(results).toHaveText(`${publicCount} agents`)
  await expect(cards).toHaveCount(publicCount)
  for (const card of await cards.all())
    await expect(card).toContainText('Healthcare and public sector')
  await screenshot(page, testInfo, 'library-filtered.png')

  await page.getByRole('searchbox', { name: 'Search agents' }).fill('renewal')
  await expect(cards).toHaveCount(1)
  await expect(cards.first()).toContainText('Benefits renewal helper')
  await page
    .getByRole('searchbox', { name: 'Search agents' })
    .fill('fictional-nothing-matches-this')
  await expect(page.getByText('No agents match these filters.')).toBeVisible()
  await page
    .locator('.library-empty')
    .getByRole('button', { name: 'Clear filters' })
    .click()
  await expect(cards).toHaveCount(templates.length)
  await expect(facet('Healthcare and public sector')).toHaveAttribute(
    'aria-pressed',
    'false',
  )
  await expectFitsViewport(page)
})

test('the library switches between cards and a list and remembers the choice', async ({
  page,
}) => {
  const state = await openLibrary(page, { ready: true })
  const view = page.getByRole('group', { name: 'View', exact: true })
  const cardsButton = view.getByRole('button', { name: 'Cards' })
  const listButton = view.getByRole('button', { name: 'List' })
  const cards = page.locator('.library-card')
  const table = page.getByRole('table', {
    name: 'Agents matching the current filters',
  })
  const rows = table.locator('tbody tr')
  const results = page.getByRole('heading', { level: 2, name: /agents?$/ })
  const stored = () =>
    page.evaluate(() => localStorage.getItem('foundry-lab-library-view'))

  await expect(cardsButton).toHaveAttribute('aria-pressed', 'true')
  await expect(listButton).toHaveAttribute('aria-pressed', 'false')
  await expect(cards).toHaveCount(templates.length)
  await expect(table).toHaveCount(0)

  await listButton.click()
  await expect(listButton).toHaveAttribute('aria-pressed', 'true')
  await expect(cardsButton).toHaveAttribute('aria-pressed', 'false')
  await expect(cards).toHaveCount(0)
  await expect(rows).toHaveCount(templates.length)
  await expect(results).toHaveText(`${templates.length} agents`)
  await expect(table.getByRole('columnheader')).toHaveText([
    'Agent',
    'Job',
    'Sector',
    'Readiness',
    'Action',
  ])
  expect(await stored()).toBe('list')
  // The one agent that is ready offers Chat; the rest open their page.
  const row = rows.filter({ hasText: support.label })
  await expect(row).toContainText(support.sector.label)
  await expect(row.getByRole('button', { name: 'Try in Chat' })).toBeVisible()
  await expect(
    table.getByRole('button', { name: 'Open', exact: true }),
  ).toHaveCount(templates.length - 1)

  // Search and the filter menus work in the list too.
  const search = page.getByRole('searchbox', { name: 'Search agents' })
  await search.fill('renewal')
  await expect(rows).toHaveCount(1)
  await expect(rows.first()).toContainText('Benefits renewal helper')
  await expect(results).toHaveText('1 agent')
  await search.fill('')
  await expect(rows).toHaveCount(templates.length)
  const strip = page.locator('.library-filter-strip')
  await expect(strip.locator('.library-filter-menu > summary')).toHaveText([
    'Sector and industry',
    'Task',
    'Readiness',
    'Works with',
  ])
  const publicCount = templates.filter(
    (item) => item.sector.id === 'public',
  ).length
  await strip.locator('.library-filter-menu > summary').first().click()
  await strip
    .locator('.library-facet')
    .filter({
      has: page.getByText('Healthcare and public sector', { exact: true }),
    })
    .click()
  await expect(rows).toHaveCount(publicCount)
  await expect(results).toHaveText(`${publicCount} agents`)
  await expect(
    strip.locator('.library-filter-menu > summary strong'),
  ).toHaveText('Healthcare and public sector')
  await page.keyboard.press('Escape')
  await strip.getByRole('button', { name: 'Clear filters' }).click()
  await expect(rows).toHaveCount(templates.length)

  // Opening an agent and coming back keeps the list.
  await row.getByRole('button', { name: support.label }).click()
  await expect(
    page.getByRole('heading', { level: 1, name: support.label, exact: true }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Back to all agents' }).click()
  await expect(rows).toHaveCount(templates.length)

  // Try in Chat loads the sample and sends nothing.
  await row.getByRole('button', { name: 'Try in Chat' }).click()
  const editor = page.getByRole('textbox', { name: 'Message', exact: true })
  await expect(editor).toHaveValue(support.sample_input)
  expect(state.chat).toHaveLength(0)
  // An unsent draft would make the reload below ask before leaving.
  await editor.fill('')

  await workspaceNav(page)
    .getByRole('button', { name: /^All agents/ })
    .click()
  await page.reload()
  await expect(listButton).toHaveAttribute('aria-pressed', 'true')
  await expect(rows).toHaveCount(templates.length)
  await cardsButton.click()
  await expect(cards).toHaveCount(templates.length)
  await expect(table).toHaveCount(0)
  expect(await stored()).toBe('cards')
  await page.reload()
  await expect(cardsButton).toHaveAttribute('aria-pressed', 'true')
  await expect(cards).toHaveCount(templates.length)
  expect(state.drafts).toBe(0)
  expect(state.creations).toBe(0)
})

test('the search hint fits inside the search box', async ({ page }) => {
  await openLibrary(page)
  const search = page.getByRole('searchbox', { name: 'Search agents' })
  await expect(search).toBeVisible()
  const { hint, room } = await search.evaluate((input: HTMLInputElement) => {
    const style = getComputedStyle(input)
    const probe = document.createElement('span')
    probe.textContent = input.placeholder
    probe.style.cssText = 'position:absolute;visibility:hidden;white-space:pre'
    probe.style.font = style.font
    input.parentElement!.append(probe)
    const hint = probe.getBoundingClientRect().width
    probe.remove()
    return {
      hint,
      room:
        input.clientWidth -
        parseFloat(style.paddingLeft) -
        parseFloat(style.paddingRight),
    }
  })
  expect(hint).toBeGreaterThan(0)
  expect(hint).toBeLessThanOrEqual(room)
})

test('sector and industry are one list that opens a sector to show its industries', async ({
  page,
}) => {
  await openLibrary(page)
  const cards = page.locator('.library-card')
  const facet = (name: string) =>
    page
      .locator('.library-facet')
      .filter({ has: page.getByText(name, { exact: true }) })
  const inSector = (id: string) =>
    templates.filter((item) => item.sector.id === id)
  const industriesIn = (id: string) => [
    ...new Set(inSector(id).map((item) => item.industry.label)),
  ]
  const priv = catalog.facets.sectors.find(
    (item: { id: string }) => item.id === 'private',
  ).label
  const publicLabel = catalog.facets.sectors.find(
    (item: { id: string }) => item.id === 'public',
  ).label
  const privateIndustries = industriesIn('private')
  const chosen = inSector('private').find(
    (item) => item.industry.id === 'finance',
  )!.industry

  await expect(page.locator('.library-filters legend')).toHaveCount(4)
  await expect(page.locator('.library-facet[data-nested]')).toHaveCount(0)
  await expect(facet(chosen.label)).toHaveCount(0)
  await expect(facet(priv)).toHaveAttribute('aria-expanded', 'false')

  await facet(priv).click()
  await expect(facet(priv)).toHaveAttribute('aria-pressed', 'true')
  await expect(facet(priv)).toHaveAttribute('aria-expanded', 'true')
  const industries = page.getByRole('group', {
    name: `Industries in ${priv}`,
  })
  await expect(industries.locator('.library-facet')).toHaveCount(
    privateIndustries.length,
  )
  await expect(cards).toHaveCount(inSector('private').length)
  await expect(facet(publicLabel)).toHaveAttribute('aria-expanded', 'false')

  await facet(chosen.label).click()
  const financeCount = templates.filter(
    (item) => item.industry.id === chosen.id,
  ).length
  await expect(facet(chosen.label)).toHaveAttribute('aria-pressed', 'true')
  await expect(facet(priv)).toHaveAttribute('aria-pressed', 'false')
  await expect(facet(priv)).toHaveAttribute('aria-expanded', 'true')
  await expect(cards).toHaveCount(financeCount)
  for (const card of await cards.all())
    await expect(card).toContainText(chosen.label)
  await expect(
    page.getByRole('heading', { level: 2, name: /agents?$/ }),
  ).toHaveText(`${financeCount} ${financeCount === 1 ? 'agent' : 'agents'}`)

  await facet(publicLabel).click()
  await expect(facet(publicLabel)).toHaveAttribute('aria-pressed', 'true')
  await expect(facet(chosen.label)).toHaveCount(0)
  await expect(cards).toHaveCount(inSector('public').length)
  await expect(
    page.getByRole('group', { name: `Industries in ${publicLabel}` }),
  ).toBeVisible()

  await page.getByRole('button', { name: 'Clear filters' }).click()
  await expect(page.locator('.library-facet[data-nested]')).toHaveCount(0)
  await expect(cards).toHaveCount(templates.length)
  await expect(facet(publicLabel)).toHaveAttribute('aria-pressed', 'false')
})

test('the filter panel fits a short window and scrolls inside itself', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 720 })
  await openLibrary(page)
  const panel = page.locator('.library-filters')
  const search = page.getByRole('searchbox', { name: 'Search agents' })
  const clear = page.getByRole('button', { name: 'Clear filters' })
  const priv = catalog.facets.sectors.find(
    (item: { id: string }) => item.id === 'private',
  ).label
  await page
    .locator('.library-facet')
    .filter({ has: page.getByText(priv, { exact: true }) })
    .click()
  await page
    .locator('.library-view')
    .evaluate((view) => view.scrollTo({ top: 300 }))

  const box = (await panel.boundingBox())!
  expect(box.y).toBeGreaterThanOrEqual(0)
  expect(box.y + box.height).toBeLessThanOrEqual(720)
  expect(await panel.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(
    true,
  )
  const facet = (await page.locator('.library-facet').first().boundingBox())!
  expect(facet.x - box.x).toBeGreaterThanOrEqual(5)

  await panel.evaluate((el) => el.scrollTo({ top: el.scrollHeight }))
  await expect(clear).toBeInViewport({ ratio: 1 })
  await panel.evaluate((el) => el.scrollTo({ top: 0 }))
  await expect(search).toBeInViewport({ ratio: 1 })

  await panel.evaluate((el) => el.scrollTo({ top: el.scrollHeight }))
  await clear.click()
  await expect(page.locator('.library-card')).toHaveCount(templates.length)
})

test('the filter panel does not scroll when the window is tall enough', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1200 })
  await openLibrary(page)
  const panel = page.locator('.library-filters')
  const priv = catalog.facets.sectors.find(
    (item: { id: string }) => item.id === 'private',
  ).label
  await page
    .locator('.library-facet')
    .filter({ has: page.getByText(priv, { exact: true }) })
    .click()
  await expect(
    page.getByRole('button', { name: 'Clear filters' }),
  ).toBeVisible()
  expect(await panel.evaluate((el) => el.scrollHeight <= el.clientHeight)).toBe(
    true,
  )
})
