import { expect, test } from '@playwright/test'
import { templates } from './helpers/catalog'
import { expectFitsViewport } from './helpers/layout'
import { openLibrary } from './helpers/library-lab'
import { libraryNav, workspaceNav } from './helpers/navigation'
import { demoScenarios } from '../src/demo-scenarios'

test('the library is the landing view and groups navigation into three sections', async ({
  page,
}) => {
  await openLibrary(page)
  await expect(
    workspaceNav(page).getByRole('button', { name: /^All agents/ }),
  ).toHaveAttribute('aria-current', 'page')
  await expect(
    workspaceNav(page).getByRole('group').locator('.nav-section-label'),
  ).toHaveText(['Agent library', 'Try it', 'Operations'])
  const tabs = libraryNav(page)
  await expect(tabs.getByRole('button')).toHaveText([
    'Browse',
    /^Ready to chat\s*1$/,
    /^Made in this Lab\s*0$/,
    'Guided demos',
    'Add-ons',
  ])
  await expect(workspaceNav(page).getByRole('button')).toHaveText([
    /^All agents\s*\d*$/,
    'Create agent',
    'Chat',
    /^Shared history/,
    'Overview',
    'Performance',
    /^Request log/,
  ])
  await expect(tabs.getByRole('button', { name: 'Browse' })).toHaveAttribute(
    'aria-current',
    'page',
  )
  await tabs.getByRole('button', { name: /^Ready to chat/ }).click()
  await expect(
    page.getByRole('heading', { level: 1, name: 'Choose an agent' }),
  ).toBeVisible()
  await expect(
    workspaceNav(page).getByRole('button', { name: /^All agents/ }),
  ).toHaveAttribute('aria-current', 'page')
  await tabs.getByRole('button', { name: 'Browse' }).click()
  for (const [name, heading] of [
    ['Chat', null],
    [/^Request log/, 'Request log'],
    ['Performance', 'Performance'],
    ['Overview', 'Operations'],
    [/^All agents/, 'Find an agent for the job'],
  ] as const) {
    await workspaceNav(page)
      .getByRole('button', { name, exact: typeof name === 'string' })
      .click()
    if (heading)
      await expect(
        page.getByRole('heading', { level: 1, name: heading }),
      ).toBeVisible()
    else
      await expect(
        page.getByRole('textbox', { name: 'Message', exact: true }),
      ).toBeVisible()
    await expect(tabs).toHaveCount(
      heading === 'Find an agent for the job' ? 1 : 0,
    )
  }
  await tabs.getByRole('button', { name: 'Guided demos' }).click()
  await expect(
    page.getByRole('heading', {
      level: 1,
      name: 'From paperwork to a clear next step.',
    }),
  ).toBeVisible()
  await expect(
    tabs.getByRole('button', { name: 'Guided demos' }),
  ).toHaveAttribute('aria-current', 'page')
  await expect(
    page.getByRole('heading', { name: 'Want a version of your own?' }),
  ).toBeVisible()
  await expect(page.getByText(/Terraform|Verified Modules/)).toHaveCount(0)
  await expect(
    workspaceNav(page).getByRole('button', { name: /^All agents/ }),
  ).toHaveAttribute('aria-current', 'page')
  for (const [hash, name] of [
    ['#library', /^All agents/],
    ['#agents', /^All agents/],
    ['#demos', /^All agents/],
    ['#operations', 'Overview'],
    ['#performance', 'Performance'],
    ['#logs', /^Request log/],
  ] as const) {
    await page.goto('/' + hash)
    await page.reload()
    await expect(
      workspaceNav(page).getByRole('button', {
        name,
        exact: typeof name === 'string',
      }),
    ).toHaveAttribute('aria-current', 'page')
  }
})

test('the Ready to chat and Made in this Lab pages explain their counts at 1 and 0', async ({
  page,
}) => {
  await openLibrary(page)
  const tabs = libraryNav(page)
  await tabs.getByRole('button', { name: /^Ready to chat/ }).click()
  const intro = page
    .getByRole('heading', { level: 1, name: 'Choose an agent' })
    .locator('xpath=..')
  await expect(intro).toContainText('1 agent is ready to chat.')
  await expect(intro).toContainText(
    'To try another library agent, open Browse and make your own copy.',
  )
  await expect(intro).not.toContainText('as previews')
  await tabs.getByRole('button', { name: /^Made in this Lab/ }).click()
  await expect(
    page.getByRole('heading', { level: 1, name: 'Made in this Lab' }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'Nothing made in this Lab yet' }),
  ).toBeVisible()
  await expect(
    page.getByText('also shows up under Ready to chat'),
  ).toBeVisible()
  await page
    .getByRole('button', { name: 'Create an agent', exact: true })
    .click()
  await expect(
    page.getByRole('heading', { level: 1, name: 'Create an agent' }),
  ).toBeVisible()
})

test('the Ready to chat page counts created agents and points to the previews', async ({
  page,
}) => {
  await openLibrary(page, { ready: true, libraryPreview: true })
  const tabs = libraryNav(page)
  await expect(tabs.getByRole('button', { name: /^Ready to chat/ })).toHaveText(
    /^Ready to chat\s*2$/,
  )
  await expect(
    tabs.getByRole('button', { name: /^Made in this Lab/ }),
  ).toHaveText(/^Made in this Lab\s*1$/)
  await tabs.getByRole('button', { name: /^Ready to chat/ }).click()
  const intro = page
    .getByRole('heading', { level: 1, name: 'Choose an agent' })
    .locator('xpath=..')
  await expect(intro).toContainText('2 agents are ready to chat.')
  await expect(intro).toContainText(
    'Library agents can be tried as previews from Browse.',
  )
  await expect(intro).not.toContainText('make your own copy')
})

test('grey placeholder cards hold the place of the agents while the library loads', async ({
  page,
}, testInfo) => {
  const state = await openLibrary(page, { slowCatalog: true })
  const placeholders = page.locator('.library-placeholder')
  const cards = page.locator('.library-card')
  const startPlaceholders = page.locator('.library-start-placeholder')
  const startCards = page.locator('.library-start-card')
  const startFirst = page.locator('.library-start-list > li').first()
  const status = page.getByText('Loading the agent library...')
  await expect(status).toBeAttached()
  await expect(
    page.getByRole('heading', { level: 1, name: 'Find an agent for the job' }),
  ).toBeVisible()
  await expect(placeholders).toHaveCount(6)
  await expect(startPlaceholders).toHaveCount(demoScenarios.length)
  await expect(cards).toHaveCount(0)
  await expect(startCards).toHaveCount(0)
  await expect(page.getByRole('alert')).toHaveCount(0)
  const waiting = (await placeholders.first().boundingBox())!
  const startWaiting = (await startFirst.boundingBox())!
  const head = (await page.locator('.library-results-head').boundingBox())!

  state.releaseCatalog()
  await expect(cards).toHaveCount(templates.length)
  await expect(placeholders).toHaveCount(0)
  await expect(startPlaceholders).toHaveCount(0)
  await expect(startCards).toHaveCount(demoScenarios.length)
  await expect(status).toHaveCount(0)
  const arrived = (await cards.first().boundingBox())!
  const startArrived = (await startFirst.boundingBox())!
  const arrivedHead = (await page
    .locator('.library-results-head')
    .boundingBox())!
  // The first card lands where its placeholder was, so the page does not jump.
  // Only the desktop layout is compared; the stacked layout at the mobile width
  // is not lined up this closely.
  if (testInfo.project.name !== 'desktop') return
  for (const edge of ['x', 'y', 'width', 'height'] as const)
    expect(
      Math.abs(startArrived[edge] - startWaiting[edge]),
      `start ${edge}`,
    ).toBeLessThanOrEqual(1)
  for (const edge of ['x', 'y', 'width'] as const)
    expect(Math.abs(arrived[edge] - waiting[edge]), edge).toBeLessThanOrEqual(1)
  expect(
    Math.abs(arrivedHead.height - head.height),
    'head',
  ).toBeLessThanOrEqual(1)
})

test('every agent card carries an icon that is only decoration', async ({
  page,
}) => {
  await openLibrary(page)
  const cards = page.locator('.library-card')
  await expect(cards).toHaveCount(templates.length)
  const icons = cards.locator('.library-card-icon')
  await expect(icons).toHaveCount(templates.length)
  for (const icon of await icons.all()) {
    await expect(icon).toHaveAttribute('aria-hidden', 'true')
    await expect(icon.locator('svg')).toHaveCount(1)
    await expect(icon).toHaveText('')
  }
})

test('Start here offers the three ready-made examples and steps aside while searching', async ({
  page,
}) => {
  const state = await openLibrary(page)
  const start = page.getByRole('region', { name: 'Start here' })
  const options = start.getByRole('button')
  await expect(start.getByRole('heading', { level: 2 })).toHaveText(
    'Start here',
  )
  await expect(options).toHaveCount(demoScenarios.length)
  for (const [index, scenario] of demoScenarios.entries()) {
    const option = options.nth(index)
    await expect(option).toContainText(scenario.title)
    await expect(option).toContainText(scenario.description)
    await expect(option).toContainText(scenario.templateLabel)
    await expect(option.locator('.library-card-icon svg')).toHaveCount(1)
  }

  const search = page.getByRole('searchbox', { name: 'Search agents' })
  await search.fill('renewal')
  await expect(page.locator('.library-card')).toHaveCount(1)
  await expect(start).toHaveCount(0)
  await search.fill('')
  await expect(start).toBeVisible()
  await page
    .locator('.library-facet')
    .filter({
      has: page.getByText('Healthcare and public sector', { exact: true }),
    })
    .click()
  await expect(start).toHaveCount(0)
  await page.getByRole('button', { name: 'Clear filters' }).click()
  await expect(start).toBeVisible()

  await options.first().click()
  await expect(
    page.getByRole('heading', {
      level: 1,
      name: demoScenarios[0].templateLabel,
      exact: true,
    }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Try it with an example' }),
  ).toBeVisible()
  // Opening an example only goes to the agent's page; nothing is sent or made.
  expect(state.chat).toHaveLength(0)
  expect(state.creations).toBe(0)
  expect(state.drafts).toBe(0)
})

test('the Add-ons tab previews what an agent could connect to without calling anything', async ({
  page,
}) => {
  const state = await openLibrary(page)
  await libraryNav(page).getByRole('button', { name: 'Add-ons' }).click()
  await expect(
    page.getByRole('heading', { level: 1, name: 'Add-ons an agent could use' }),
  ).toBeVisible()
  await expect(
    workspaceNav(page).getByRole('button', {
      name: 'All agents',
    }),
  ).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('note')).toContainText('A preview only.')
  await expect(page.getByRole('note')).toContainText(
    'Knowledge search, already runs as a small sample pilot',
  )

  const cards = page.locator('.addon-card')
  await expect(cards.getByRole('heading', { level: 2 })).toHaveText([
    'Knowledge search',
    'Conversation memory',
    'Document extraction',
    'Notifications',
    'Code interpreter',
    'Web search',
  ])
  await expect(cards.getByText('Not available yet')).toHaveCount(5)
  await expect(cards.getByText('Sample pilot')).toHaveCount(1)
  await expect(cards.first().getByText('Sample pilot')).toBeVisible()
  await expect(cards.getByText('In the Lab today')).toHaveCount(1)
  await expect(cards.first()).toContainText('ten approved sample passages')
  for (const heading of [
    'What it would cost',
    'What it would need',
    'Keeping it safe',
  ])
    await expect(cards.getByRole('heading', { name: heading })).toHaveCount(6)
  await expect(page.locator('.library-badge.caution')).toHaveText(
    'Needs data-handling approval first',
  )
  await expect(
    page.getByRole('heading', { name: /Rules every add-on would follow/ }),
  ).toBeVisible()

  await expect(cards.first().getByText('Azure AI Search')).toBeVisible()
  await expect(cards.first()).toContainText('Add-ons roadmap (#54)')

  expect(state.chat).toHaveLength(0)
  expect(state.creations).toBe(0)
  expect(state.drafts).toBe(0)
  await expectFitsViewport(page)

  await page.goto('/#library')
  await page.reload()
  await page.goto('/#addons')
  await page.reload()
  await expect(
    page.getByRole('heading', { level: 1, name: 'Add-ons an agent could use' }),
  ).toBeVisible()
})
