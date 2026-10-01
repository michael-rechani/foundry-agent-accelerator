import { expect, test, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import type { CreatedAgent } from '../src/agent-creation-client'
import { demoScenarios } from '../src/demo-scenarios'
import type { LibraryTemplate } from '../src/library-catalog'
import type { Config } from '../src/workspace-config'
import { docsScreenshot, guidedReview, screenshot } from './fixtures'

const catalog = JSON.parse(
  await readFile(
    new URL('./agent-templates.fixture.json', import.meta.url),
    'utf8',
  ),
)
const scorecards = JSON.parse(
  await readFile(
    new URL('../../agent_scorecards.json', import.meta.url),
    'utf8',
  ),
)
const templates: LibraryTemplate[] = catalog.templates
const support = templates.find((item) => item.id === 'customer-support-brief')!
const runtimeHash = 'a'.repeat(64)
const portal =
  'https://ai.azure.com/nextgen/r/qqqqqru7TMyN3e7u7u7u7g,rg-lab,,lab-account,lab-project'

function readyRecord(template: LibraryTemplate): CreatedAgent {
  const id = 'created-12345678-1234-4234-9234-123456789abc'
  const runtime = 'lab-demo-12345678123442349234123456789abc'
  return {
    id,
    name: 'Support handoff helper',
    template_id: template.id,
    template_label: template.label,
    instructions: template.instructions,
    runtime_name: runtime,
    version: '1',
    model: 'demo-reasoning-model',
    model_profile: template.model_profile,
    status: 'ready',
    stage: 'ready',
    operation: 'create',
    created_at: '2027-04-12T10:00:00Z',
    updated_at: '2027-04-12T10:00:01Z',
    _etag: '"v1"',
    error: null,
    events: [{ name: 'ready', at: '2027-04-12T10:00:01Z' }],
    agent: {
      id,
      agent: runtime,
      label: 'Support handoff helper',
      category: 'Made in this Lab',
      description: template.description,
      tools: {},
      prompts: [{ label: 'Try the sample', text: template.sample_input }],
      guidance: {
        input: template.input,
        output: template.output,
        limits: template.limits,
        delegation: template.delegation,
        configuration:
          'Saved task setup; the operator controls the model and fixed runtime tools.',
      },
    },
  }
}

async function setup(
  page: Page,
  options: {
    ready?: boolean
    preview?: boolean
    hash?: string
    catalogFailure?: boolean
    portal?: boolean
    withoutResultsFor?: string
    libraryPreview?: boolean
    stallChat?: boolean
    slowCatalog?: boolean
  } = {},
) {
  const served = {
    ...scorecards,
    scorecards: scorecards.scorecards.filter(
      (card: { template_id: string }) =>
        card.template_id !== options.withoutResultsFor,
    ),
  }
  const config: Config = {
    title: 'Foundry Agent Lab',
    mode: options.preview ? 'preview' : 'private',
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
    foundry_portal: options.portal ? portal : null,
    ...(options.libraryPreview
      ? {
          library_preview: {
            enabled: true,
            reason: null,
            agent: 'lab-preview-agent',
          },
        }
      : {}),
    agent_creation: {
      enabled: !options.preview,
      storage_enabled: !options.preview,
      management_enabled: !options.preview,
      reason: options.preview ? 'local_preview' : null,
      requires_operator_key: true,
      max_agents: 5,
      publication_timeout_seconds: 600,
      model: options.preview ? null : 'demo-model',
      models: options.preview
        ? null
        : {
            reasoning: 'demo-reasoning-model',
            extraction: 'demo-fast-model',
            tool_calling: 'demo-model',
          },
    },
  }
  const record = options.ready
    ? { ...readyRecord(support), runtime_hash: runtimeHash }
    : null
  let releaseCatalog = () => {}
  const catalogGate = options.slowCatalog
    ? new Promise<void>((resolve) => {
        releaseCatalog = resolve
      })
    : null
  const state = {
    chat: [] as { agent_id: string; input: string }[],
    drafts: 0,
    creations: 0,
    catalogRequests: 0,
    failCatalog: !!options.catalogFailure,
    failScorecards: false,
    releaseCatalog,
  }
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const method = request.method()
    const respond = (json: unknown, status = 200) =>
      route.fulfill({ json, status })
    if (path === '/api/config') return respond(config)
    if (path === '/api/agent-templates') {
      state.catalogRequests++
      expect(request.headers()['x-workbench-request']).toBe('1')
      if (state.failCatalog) return respond({ error: 'agents_busy' }, 429)
      if (catalogGate) await catalogGate
      return respond(catalog)
    }
    if (path === '/api/agent-scorecards') {
      if (state.failScorecards) return respond({ error: 'agents_busy' }, 429)
      return respond(served)
    }
    if (path === '/api/agents' && method === 'GET')
      return respond({ items: record ? [record] : [], limit: 5 })
    if (path === '/api/agents' && method === 'POST') {
      state.creations++
      return respond({ error: 'operator_access_required' }, 403)
    }
    if (path === '/api/agent-drafts') {
      state.drafts++
      return respond({ error: 'template_required' }, 400)
    }
    if (record && path === `/api/agents/${record.id}`) return respond(record)
    if (path === '/api/reviews') {
      const body = request.postDataJSON()
      state.chat.push(body)
      if (options.stallChat) return
      return respond({
        request_id: 'fictional-request-0001',
        status: 'completed',
        agent: record?.runtime_name || guidedReview.agent,
        text: 'ILLUSTRATIVE ANSWER: GRANT-2 claims 40 sessions; ATTENDANCE-1 shows 32. A person decides compliance.',
        elapsed_ms: 900,
        receipts: [],
      })
    }
    return respond({ error: 'not_found' }, 404)
  })
  await page.goto('/' + (options.hash ?? ''))
  await expect(
    page.getByRole('navigation', { name: 'Workspace' }),
  ).toBeVisible()
  return state
}

const navigation = (page: Page) =>
  page.getByRole('navigation', { name: 'Workspace' })

async function openAgent(page: Page, label: string) {
  await page.locator('.library-card').filter({ hasText: label }).click()
  await expect(
    page.getByRole('heading', { level: 1, name: label, exact: true }),
  ).toBeVisible()
}

test('the library is the landing view and groups navigation into four sections', async ({
  page,
}) => {
  await setup(page)
  await expect(
    navigation(page).getByRole('button', { name: 'All agents' }),
  ).toHaveAttribute('aria-current', 'page')
  await expect(
    navigation(page).getByRole('group').locator('.nav-section-label'),
  ).toHaveText(['Agent library', 'Try it', 'Measure', 'Activity'])
  const tabs = page.getByRole('navigation', { name: 'Agent library' })
  await expect(tabs.getByRole('button')).toHaveText([
    'Browse',
    /^Ready to chat\s*1$/,
    /^Made in this Lab\s*0$/,
    'Guided demos',
    'Add-ons',
  ])
  await expect(navigation(page).getByRole('button')).toHaveText([
    'All agents',
    'Create agent',
    'Chat',
    'Shared history',
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
    navigation(page).getByRole('button', { name: 'All agents' }),
  ).toHaveAttribute('aria-current', 'page')
  await tabs.getByRole('button', { name: 'Browse' }).click()
  for (const [name, heading] of [
    ['Chat', null],
    [/^Request log/, 'Request log'],
    ['Performance', 'Performance'],
    ['All agents', 'Find an agent for the job'],
  ] as const) {
    await navigation(page)
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
    await expect(tabs).toHaveCount(name === 'All agents' ? 1 : 0)
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
    navigation(page).getByRole('button', { name: 'All agents' }),
  ).toHaveAttribute('aria-current', 'page')
  for (const [hash, name] of [
    ['#library', 'All agents'],
    ['#agents', 'All agents'],
    ['#demos', 'All agents'],
    ['#performance', 'Performance'],
    ['#logs', /^Request log/],
  ] as const) {
    await page.goto('/' + hash)
    await page.reload()
    await expect(
      navigation(page).getByRole('button', {
        name,
        exact: typeof name === 'string',
      }),
    ).toHaveAttribute('aria-current', 'page')
  }
})

test('the Ready to chat and Made in this Lab pages explain their counts at 1 and 0', async ({
  page,
}) => {
  await setup(page)
  const tabs = page.getByRole('navigation', { name: 'Agent library' })
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
  await setup(page, { ready: true, libraryPreview: true })
  const tabs = page.getByRole('navigation', { name: 'Agent library' })
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
  const state = await setup(page, { slowCatalog: true })
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
  await setup(page)
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
  const state = await setup(page)
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
  const state = await setup(page)
  await page
    .getByRole('navigation', { name: 'Agent library' })
    .getByRole('button', { name: 'Add-ons' })
    .click()
  await expect(
    page.getByRole('heading', { level: 1, name: 'Add-ons an agent could use' }),
  ).toBeVisible()
  await expect(
    page.getByRole('navigation', { name: 'Workspace' }).getByRole('button', {
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
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)

  await page.goto('/#library')
  await page.reload()
  await page.goto('/#addons')
  await page.reload()
  await expect(
    page.getByRole('heading', { level: 1, name: 'Add-ons an agent could use' }),
  ).toBeVisible()
})

test('browse, filter and search the catalog with live counts', async ({
  page,
}, testInfo) => {
  await setup(page)
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
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
})

test('the search hint fits inside the search box', async ({ page }) => {
  await setup(page)
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
  await setup(page)
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
  await setup(page)
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
  await setup(page)
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

test('details state limits, human decisions and never claim a recorded answer', async ({
  page,
}) => {
  const state = await setup(page)
  await openAgent(page, support.label)
  await expect(page.locator('.library-decision')).toContainText(
    support.human_decision,
  )
  const tabs = page.getByRole('tablist', { name: 'Agent details' })
  await expect(tabs.getByRole('tab')).toHaveText([
    'Overview',
    'Try it',
    'Test results',
    'Take it to Foundry',
  ])
  await expect(tabs.getByRole('tab', { name: 'Overview' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  const panel = page.getByRole('tabpanel')
  await expect(panel).toContainText(support.limits)
  await expect(panel).toContainText(support.expected_behavior)
  await expect(panel).toContainText(
    'Based on its acceptance tests, not a recorded answer.',
  )
  for (const item of support.prerequisites)
    await expect(panel).toContainText(item)

  await tabs.getByRole('tab', { name: 'Take it to Foundry' }).click()
  await expect(panel).toContainText(
    'There is no one-click cross-environment deployment.',
  )
  await expect(panel.locator('.library-command')).toContainText(
    `bundle.py export-created --record ${support.id}-record.json`,
  )
  await expect(
    panel.getByRole('button', { name: 'Create this agent first' }),
  ).toBeEnabled()

  await page.getByRole('button', { name: 'Back to all agents' }).click()
  await expect(page.locator('.library-card')).toHaveCount(templates.length)
  expect(state.chat).toHaveLength(0)
  expect(state.drafts).toBe(0)
  expect(state.creations).toBe(0)
})

test('creating from the library preselects the template without preparing or publishing', async ({
  page,
}) => {
  const state = await setup(page)
  await openAgent(page, support.label)
  await page.getByRole('tab', { name: 'Try it' }).click()
  await page
    .getByRole('button', { name: 'Create this agent to test it' })
    .click()
  await expect(
    page.getByRole('heading', { name: 'Create an agent', exact: true }),
  ).toBeVisible()
  await expect(
    page.locator('.creation-template[aria-pressed="true"]'),
  ).toContainText(support.label)
  await expect(
    page.getByRole('textbox', { name: 'What should the agent help with?' }),
  ).toHaveValue(support.example_request)
  await expect(
    page.getByRole('combobox', { name: 'Prepared template' }),
  ).toHaveValue(support.id)
  expect(state.drafts).toBe(0)
  expect(state.creations).toBe(0)
})

test('a created agent opens in Chat as a draft and its request is logged and measured', async ({
  page,
  context,
}, testInfo) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  const state = await setup(page, { ready: true })
  await expect(
    page.locator('.library-card').filter({ hasText: support.label }),
  ).toContainText('Made in this Lab')
  await openAgent(page, support.label)
  await page.getByRole('tab', { name: 'Try it' }).click()
  await expect(page.getByRole('tabpanel')).toContainText(
    'Nothing happens until you press Send',
  )
  await page.getByRole('button', { name: 'Open your created agent' }).click()
  const editor = page.getByRole('textbox', { name: 'Message', exact: true })
  await expect(editor).toHaveValue(support.sample_input)
  await expect(page.locator('.agent-picker')).toContainText(
    'Support handoff helper',
  )
  expect(state.chat).toHaveLength(0)

  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.getByText('ILLUSTRATIVE ANSWER')).toBeVisible()
  expect(state.chat).toHaveLength(1)
  expect(state.chat[0].agent_id).toBe(readyRecord(support).id)

  const log = navigation(page).getByRole('button', { name: /^Request log/ })
  await expect(log).toContainText('1')
  await log.click()
  const row = page
    .getByRole('table', { name: 'Request log' })
    .locator('tbody tr')
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('Support handoff helper')
  await expect(row).toContainText('Completed')
  await row.getByRole('button', { name: /fictional-request-0001/ }).click()
  await expect(page.getByText('Reference copied.')).toBeVisible()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
    'fictional-request-0001',
  )
  await screenshot(page, testInfo, 'request-log.png')

  await navigation(page)
    .getByRole('button', { name: 'Performance', exact: true })
    .click()
  await expect(page.locator('.metric-strip-4 > div')).toHaveCount(4)
  await expect(
    page.getByRole('table', { name: 'Recent requests' }),
  ).toContainText('Support handoff helper')
  await expect(page.locator('.table-note').last()).toContainText(
    'choose Test results',
  )
  await screenshot(page, testInfo, 'performance.png')
})

test('export downloads the saved ready record needed by export-created', async ({
  page,
}) => {
  await setup(page, { ready: true })
  await openAgent(page, support.label)
  await page.getByRole('tab', { name: 'Take it to Foundry' }).click()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download saved record' }).click()
  const file = await download
  expect(file.suggestedFilename()).toBe(`${support.id}-record.json`)
  const saved = JSON.parse(await readFile(await file.path(), 'utf8'))
  expect(saved).toMatchObject({
    status: 'ready',
    template_id: support.id,
    runtime_hash: runtimeHash,
    model: 'demo-reasoning-model',
  })
  await expect(page.getByRole('status')).toContainText(
    'Saved record downloaded.',
  )
})

test('take it to Foundry downloads the definition and test requests without creating anything', async ({
  page,
}) => {
  const state = await setup(page)
  const agent = templates.find((item) => item.id === 'casework-assistant')!
  await openAgent(page, agent.label)
  await page.getByRole('tab', { name: 'Take it to Foundry' }).click()
  const panel = page.getByRole('tabpanel')

  const definitionDownload = page.waitForEvent('download')
  await panel.getByRole('button', { name: 'Download agent definition' }).click()
  const definitionFile = await definitionDownload
  expect(definitionFile.suggestedFilename()).toBe(
    'casework-assistant.foundry-agent.json',
  )
  const definition = JSON.parse(
    await readFile(await definitionFile.path(), 'utf8'),
  )
  expect(definition.definition).toEqual({
    kind: 'prompt',
    model: '<your-model-deployment>',
    instructions: agent.instructions,
    tools: [],
  })
  expect(definition.metadata.library_agent).toBe(agent.id)
  await expect(page.getByRole('status')).toContainText(
    'Agent definition downloaded.',
  )

  const cases = scorecards.scorecards.find(
    (card: { template_id: string }) => card.template_id === agent.id,
  ).cases
  await expect(panel).toContainText(
    `${cases.length} requests for a Foundry evaluation`,
  )
  const casesDownload = page.waitForEvent('download')
  await panel.getByRole('button', { name: 'Download test requests' }).click()
  const casesFile = await casesDownload
  expect(casesFile.suggestedFilename()).toBe(
    'casework-assistant.foundry-test-cases.jsonl',
  )
  const rows = (await readFile(await casesFile.path(), 'utf8'))
    .trimEnd()
    .split('\n')
    .map((line) => JSON.parse(line))
  expect(rows).toHaveLength(cases.length)
  expect(rows[0]).toEqual({
    query: cases[0].input,
    case_id: cases[0].id,
    category: cases[0].category,
    expected_behavior: cases[0].goal,
  })
  await expect(page.getByRole('status')).toContainText(
    'Test requests downloaded.',
  )
  expect(state.creations).toBe(0)
  expect(state.drafts).toBe(0)
})

test('an agent without test results still offers its definition', async ({
  page,
}) => {
  await setup(page, { withoutResultsFor: support.id })
  await openAgent(page, support.label)
  await page.getByRole('tab', { name: 'Take it to Foundry' }).click()
  const panel = page.getByRole('tabpanel')
  await expect(panel).toContainText('This agent has no test requests yet.')
  await expect(
    panel.getByRole('button', { name: 'Download test requests' }),
  ).toHaveCount(0)
  await expect(
    panel.getByRole('button', { name: 'Download agent definition' }),
  ).toBeEnabled()
})

test('test requests that fail to load can be retried', async ({ page }) => {
  const state = await setup(page)
  state.failScorecards = true
  await openAgent(page, 'Case summary writer')
  await page.getByRole('tab', { name: 'Take it to Foundry' }).click()
  const panel = page.getByRole('tabpanel')
  await expect(panel).toContainText('The test requests did not load.')
  await expect(
    panel.getByRole('button', { name: 'Download agent definition' }),
  ).toBeEnabled()
  state.failScorecards = false
  await panel.getByRole('button', { name: 'Try again' }).click()
  await expect(
    panel.getByRole('button', { name: 'Download test requests' }),
  ).toBeEnabled()
})

test('a created agent links to Foundry only under the hood', async ({
  page,
}) => {
  await setup(page, { ready: true, portal: true })
  await openAgent(page, support.label)
  await page.getByRole('tab', { name: 'Take it to Foundry' }).click()
  const link = page.getByRole('link', { name: /Open this agent in Foundry/ })
  await expect(link).toHaveAttribute(
    'href',
    `${portal}/build/agents/lab-demo-12345678123442349234123456789abc/build`,
  )
  await page.getByRole('switch', { name: /Under the hood/ }).uncheck()
  await expect(link).toBeHidden()
})

test('preview explains that nothing is published and catalog failures can be retried', async ({
  page,
}) => {
  const state = await setup(page, { preview: true, catalogFailure: true })
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(
    page.getByRole('heading', { level: 1, name: 'Agent library' }),
  ).toBeVisible()
  state.failCatalog = false
  await page.getByRole('button', { name: 'Retry' }).click()
  await expect(page.locator('.library-card')).toHaveCount(templates.length)
  await openAgent(page, support.label)
  await page.getByRole('tab', { name: 'Try it' }).click()
  await expect(page.getByRole('tabpanel')).toContainText(
    'Local preview: you can prepare and review a setup, but nothing is published.',
  )
  await navigation(page)
    .getByRole('button', { name: /^Request log/ })
    .click()
  await expect(page.locator('.secondary-view')).toContainText(/preview/i)
})

test('a library preview says what the agent will return while the answer is on its way', async ({
  page,
}) => {
  await page.clock.install()
  const state = await setup(page, { libraryPreview: true, stallChat: true })
  await openAgent(page, support.label)
  await page.getByRole('tab', { name: 'Try it' }).click()
  await page.getByRole('button', { name: 'Try it now in Chat' }).click()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue(support.sample_input)
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => state.chat.length).toBe(1)
  expect(state.chat[0].agent_id).toBe(`library-${support.id}`)
  const waiting = page.getByRole('status').filter({ hasText: 'Awaiting' })
  await expect(waiting).toContainText(support.label)
  await expect(waiting).toContainText('What you get')
  await expect(waiting).toContainText(support.output)
  await expect(waiting).not.toContainText('Still working')
})

test('with library previews on, the invoice guided demo runs as a library preview', async ({
  page,
}) => {
  const invoice = demoScenarios.find((item) => item.id === 'invoice')!
  const state = await setup(page, { libraryPreview: true, hash: '#demos' })
  await page
    .getByRole('navigation', { name: 'Demo scenarios' })
    .getByRole('button', { name: /Supplier invoice review/ })
    .click()
  const note = page.locator('.demo-execution-note')
  await expect(note).toContainText(
    `Uses the ${invoice.templateLabel} library preview.`,
  )
  await expect(note).toContainText('Preview chats are not saved.')
  await expect(
    page.getByRole('button', { name: `Choose ${invoice.templateLabel}` }),
  ).toHaveCount(0)
  await page.getByRole('button', { name: 'Load sample input' }).click()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue(invoice.input)
  await expect(page.locator('.agent-picker')).toContainText(
    invoice.templateLabel,
  )
  expect(state.chat).toEqual([])
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => state.chat.length).toBe(1)
  expect(state.chat[0]).toMatchObject({
    agent_id: 'library-supplier-invoice-reviewer',
    input: invoice.input,
  })
})

test('without library previews, the invoice guided demo still offers to create the agent', async ({
  page,
}) => {
  const invoice = demoScenarios.find((item) => item.id === 'invoice')!
  const state = await setup(page, { hash: '#demos' })
  await page
    .getByRole('navigation', { name: 'Demo scenarios' })
    .getByRole('button', { name: /Supplier invoice review/ })
    .click()
  await expect(
    page.getByRole('button', { name: `Choose ${invoice.templateLabel}` }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Load sample input' }),
  ).toHaveCount(0)
  expect(state.chat).toEqual([])
})

for (const mode of ['light', 'dark'] as const)
  test(`library detail is readable in ${mode} mode`, async ({
    page,
  }, testInfo) => {
    await page.addInitScript((mode) => {
      localStorage.setItem(
        'ai-foundry-lab-theme',
        JSON.stringify({ mode, accent: 'foundry' }),
      )
    }, mode)
    await setup(page, { ready: true })
    await expect(page.locator('html')).toHaveAttribute('data-theme', mode)
    await openAgent(page, support.label)
    const contrast = await page.locator('.library-lede').evaluate((element) => {
      const luminance = (color: string) => {
        const [r, g, b] = color
          .match(/[\d.]+/g)!
          .slice(0, 3)
          .map((value) => {
            const channel = Number(value) / 255
            return channel <= 0.04045
              ? channel / 12.92
              : ((channel + 0.055) / 1.055) ** 2.4
          })
        return r * 0.2126 + g * 0.7152 + b * 0.0722
      }
      let node: Element | null = element
      let background = 'rgba(0, 0, 0, 0)'
      while (node && /rgba\(.*, 0\)$/.test(background)) {
        background = getComputedStyle(node).backgroundColor
        node = node.parentElement
      }
      const values = [
        luminance(getComputedStyle(element).color),
        luminance(background),
      ].sort((a, b) => b - a)
      return (values[0] + 0.05) / (values[1] + 0.05)
    })
    expect(contrast).toBeGreaterThanOrEqual(4.5)
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true)
    await screenshot(page, testInfo, `library-detail-${mode}.png`)
  })

// The README and docs pictures: the plain view a first-time visitor sees.
const tourAgent = templates.find(
  (item) => item.id === 'supplier-invoice-reviewer',
)!

for (const mode of ['light', 'dark'] as const)
  test(`the library tour shows Browse, Test results and Take it to Foundry in ${mode} mode`, async ({
    page,
  }, testInfo) => {
    const suffix = mode === 'dark' ? '-dark' : ''
    await page.addInitScript((mode) => {
      localStorage.setItem(
        'ai-foundry-lab-theme',
        JSON.stringify({ mode, accent: 'foundry' }),
      )
    }, mode)
    const state = await setup(page)
    await expect(page.locator('html')).toHaveAttribute('data-theme', mode)
    await expect(page.locator('.library-card')).toHaveCount(templates.length)
    await expect(page.getByRole('region', { name: 'Start here' })).toBeVisible()
    await docsScreenshot(page, testInfo, `library-browse${suffix}.png`)

    await openAgent(page, tourAgent.label)
    const tabs = page.getByRole('tablist', { name: 'Agent details' })
    const panel = page.getByRole('tabpanel')
    await tabs.getByRole('tab', { name: 'Test results' }).click()
    await expect(panel).toContainText('25 of 25 answers passed')
    await expect(panel).toContainText('Waiting for a person')
    await docsScreenshot(page, testInfo, `library-test-results${suffix}.png`)

    await tabs.getByRole('tab', { name: 'Take it to Foundry' }).click()
    await expect(
      panel.getByRole('button', { name: 'Download agent definition' }),
    ).toBeEnabled()
    await docsScreenshot(page, testInfo, `library-take-to-foundry${suffix}.png`)
    // Looking around sends nothing and makes nothing.
    expect(state.chat).toHaveLength(0)
    expect(state.drafts).toBe(0)
    expect(state.creations).toBe(0)
  })

for (const mode of ['light', 'dark'] as const)
  test(`the Create agent page offers every library template in three groups in ${mode} mode`, async ({
    page,
  }, testInfo) => {
    await page.addInitScript((mode) => {
      localStorage.setItem(
        'ai-foundry-lab-theme',
        JSON.stringify({ mode, accent: 'foundry' }),
      )
    }, mode)
    const state = await setup(page, { hash: '#create' })
    await expect(page.locator('html')).toHaveAttribute('data-theme', mode)
    const cards = page.locator('.creation-template')
    await expect(cards).toHaveCount(templates.length)
    await expect(page.locator('.creation-template-group h2')).toHaveText([
      'Works in any sector',
      'Private sector',
      'Healthcare and public sector',
    ])
    if (mode === 'dark') {
      await cards.nth(1).click()
      await expect(page.locator('.creation-template-check')).toHaveCount(1)
    }
    await page.evaluate(() => {
      document.querySelector('.creation-workspace')!.scrollTop = 0
    })
    await docsScreenshot(
      page,
      testInfo,
      `library-create-agent${mode === 'dark' ? '-dark' : ''}.png`,
    )
    expect(state.drafts).toBe(0)
    expect(state.creations).toBe(0)
  })
