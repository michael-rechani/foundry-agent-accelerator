import { expect, test, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import type { CreatedAgent } from '../src/agent-creation-client'
import type { LibraryTemplate } from '../src/library-catalog'
import type { Config } from '../src/workspace-config'
import { guidedReview, illustrativeScreenshot } from './fixtures'

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
  'https://ai.azure.com/nextgen/r/2gTvLTQRRlqW0WfHU1ZyCg,rg-lab,,lab-account,lab-project'

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
      category: 'Created in this Lab',
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
  } = {},
) {
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
  const state = {
    chat: [] as { agent_id: string; input: string }[],
    drafts: 0,
    creations: 0,
    catalogRequests: 0,
    failCatalog: !!options.catalogFailure,
    failScorecards: false,
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
      return respond(catalog)
    }
    if (path === '/api/agent-scorecards') {
      if (state.failScorecards) return respond({ error: 'agents_busy' }, 429)
      return respond(scorecards)
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

test('browse, filter and search the catalog with live counts', async ({
  page,
}, testInfo) => {
  await setup(page)
  const results = page.getByRole('heading', { level: 2, name: /agents?$/ })
  const cards = page.locator('.library-card')
  await expect(results).toHaveText(`${templates.length} agents`)
  await expect(cards).toHaveCount(templates.length)
  await expect(page.locator('.library-filters legend')).toHaveText([
    'Sector',
    'Industry',
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
  await illustrativeScreenshot(page, testInfo, 'library-filtered.png')

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
  await illustrativeScreenshot(page, testInfo, 'request-log.png')

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
  await illustrativeScreenshot(page, testInfo, 'performance.png')
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
  await setup(page)
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
    await illustrativeScreenshot(page, testInfo, `library-detail-${mode}.png`)
  })
