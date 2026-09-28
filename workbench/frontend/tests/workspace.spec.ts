import { expect, test, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import type { Receipt, Turn } from '../src/conversation-types'
import type { Config } from '../src/workspace-config'
import { guidedReview, illustrativeScreenshot, registry } from './fixtures'
const agent = {
  ...guidedReview,
  prompts: [
    {
      label: 'Check against a checklist',
      text: 'Synthetic configured starter',
    },
  ],
}
type Document = {
  id: string
  _etag: string
  title: string
  agent_id: string
  updated_at: string
  turns: Turn[]
}

async function workspace(
  page: Page,
  options: {
    conflict?: boolean
    stalledHistory?: boolean
    stalledReview?: boolean
    gatewayError?: boolean
    preview?: boolean
    startup?: 'stalled' | 'invalid' | 'invalid-guidance' | 'failed'
    config?: Partial<Config>
    receipts?: Receipt[]
    usage?: unknown
  } = {},
) {
  const config: Config = {
    title: 'Foundry Agent Lab',
    mode: options.preview ? 'preview' : 'private',
    agents: [agent],
    default_agent: agent.id,
    max_characters: 60000,
    max_request_bytes: 65536,
    max_history_turns: 10,
    review_timeout_ms: 190000,
    history_timeout_ms: 45000,
    retention_days: 30,
    history_enabled: !options.preview,
    ...options.config,
  }
  const state = {
    configRequests: 0,
    document: null as Document | null,
    requests: [] as {
      history: { role: string; content: string }[]
      thread: string
    }[],
    saves: [] as { turns: Turn[] }[],
    updates: [] as string[],
    deletes: [] as string[],
  }
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const respond = (json: unknown, status = 200) =>
      route.fulfill({ json, status })
    if (path === '/api/config') {
      state.configRequests++
      if (state.configRequests === 1) {
        if (options.startup === 'stalled') return
        if (options.startup === 'invalid')
          return respond({ ...config, max_request_bytes: null })
        if (options.startup === 'invalid-guidance')
          return respond({
            ...config,
            agents: [{ ...agent, guidance: { input: 'Incomplete guide' } }],
          })
        if (options.startup === 'failed')
          return respond({ error: 'unavailable' }, 503)
      }
      return respond(config)
    }
    if (path === '/api/reviews') {
      state.requests.push(request.postDataJSON())
      if (options.stalledReview) return
      if (options.gatewayError)
        return route.fulfill({
          status: 502,
          contentType: 'text/html',
          body: '<html><body>Bad Gateway</body></html>',
        })
      if (options.preview) return respond({ error: 'preview_only' }, 503)
      return respond({
        request_id: `request-${state.requests.length}`,
        status: 'completed',
        agent: (
          config.agents.find((item) => item.id === config.default_agent) ??
          agent
        ).agent,
        text: 'Section 1 is missing a budget.',
        elapsed_ms: 1000,
        ...(options.usage !== undefined ? { usage: options.usage } : {}),
        receipts: options.receipts ?? [
          {
            tool: 'inspect_application',
            call_id: 'call-1',
            verified: true,
            agent: 'application-review-agent',
            output: 'Budget missing.',
          },
        ],
      })
    }
    if (path === '/api/conversations' && request.method() === 'GET') {
      if (options.stalledHistory) return
      return respond({
        items: state.document ? [state.document] : [],
        cursor: null,
      })
    }
    if (path === '/api/review-runs' && request.method() === 'GET')
      return respond({ items: [], cursor: null })
    if (
      path.startsWith('/api/conversations') &&
      ['POST', 'PUT'].includes(request.method())
    ) {
      const body = request.postDataJSON()
      state.saves.push(body)
      if (request.method() === 'PUT') {
        state.updates.push(request.headers()['if-match'])
        if (options.conflict)
          return respond({ error: 'conversation_changed' }, 409)
      }
      state.document = {
        ...body,
        id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
        _etag: request.method() === 'PUT' ? 'v2' : 'v1',
        title: body.turns[0].question,
        updated_at: '2026-09-05T00:00:00Z',
      }
      return respond(state.document)
    }
    if (state.document && path.endsWith(state.document.id)) {
      if (request.method() === 'DELETE') {
        state.deletes.push(request.headers()['if-match'])
        state.document = null
        return respond({ deleted: true })
      }
      return respond(state.document)
    }
    return respond({ error: 'unexpected_test_request' }, 404)
  })
  await page.goto('/#chat')
  if (options.startup) await expect.poll(() => state.configRequests).toBe(1)
  else
    await expect(page.locator('.agent-picker')).toContainText(
      config.agents.find((item) => item.id === config.default_agent)!.label,
    )
  return state
}

async function send(page: Page, text = 'Review synthetic APP-1') {
  await page.getByRole('textbox', { name: 'Message' }).fill(text)
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(
    page.getByRole('button', { name: 'Save to shared history' }),
  ).toBeEnabled()
}

async function openReadyAgents(page: Page) {
  await page
    .getByRole('navigation', { name: 'Workspace' })
    .getByRole('button', { name: 'All agents' })
    .click()
  await page
    .getByRole('navigation', { name: 'Agent library' })
    .getByRole('button', { name: /^Ready to chat/ })
    .click()
}

test('shared privacy notice is visible before sending or saving', async ({
  page,
}, testInfo) => {
  await workspace(page)
  const notice = page.locator('#chat-privacy')
  await expect(notice).toBeVisible()
  await expect(notice).toBeInViewport({ ratio: 1 })
  await expect(notice).toContainText(
    'never personal or confidential information',
  )
  await expect(notice).toContainText(
    'Saving shares completed messages with everyone in this Lab for 30 days after the last update.',
  )
  await expect(page.getByRole('textbox', { name: 'Message' })).toHaveAttribute(
    'aria-describedby',
    /chat-privacy/,
  )
  await expect(
    page.getByRole('button', { name: 'Save to shared history' }),
  ).toHaveAttribute('aria-describedby', 'chat-privacy')
  await page.screenshot({
    path: testInfo.outputPath('chat-privacy-mocked-apis.png'),
    fullPage: true,
    animations: 'disabled',
  })
})

test('preview chat does not promise shared persistence', async ({ page }) => {
  await workspace(page, { preview: true })
  await expect(page.locator('#chat-privacy')).toHaveCount(0)
})

test('storage-disabled chat does not promise shared persistence', async ({
  page,
}) => {
  await workspace(page, { config: { history_enabled: false } })
  await expect(page.locator('#chat-privacy')).toBeVisible()
  await expect(page.locator('#chat-privacy')).not.toContainText('Saving shares')
})

test('chat starts with focused controls and preserves drafts when choosing an agent', async ({
  page,
}) => {
  const state = await workspace(page)
  await expect(
    page.getByRole('heading', {
      name: 'Application and case helper',
      exact: true,
    }),
  ).toBeVisible()
  await expect(
    page.getByText('Foundry Agent Lab', { exact: true }),
  ).toHaveCount(1)
  await expect(page.locator('body')).not.toContainText(
    /A LITTLE CONTEXT|Evidence-grounded\. Human-reviewed\.|CURRENT CONVERSATION/,
  )
  await expect(
    page.locator('.conversation-heading, .composer-footnote'),
  ).toHaveCount(0)
  await expect(page.locator('#context-budget')).toHaveCount(0)
  await expect(page.getByText('Not saved', { exact: true })).toHaveCount(0)

  await page
    .getByRole('button', { name: 'Check against a checklist', exact: true })
    .click()
  const editor = page.getByRole('textbox', { name: 'Message', exact: true })
  await expect(editor).toHaveValue('Synthetic configured starter')
  await expect(editor).toBeFocused()
  await expect(page.getByText('Not saved', { exact: true })).toHaveCount(0)
  await expect(page.locator('#context-budget')).toHaveCount(0)

  await page
    .getByRole('banner')
    .getByTitle('Choose an agent', { exact: true })
    .click()
  const switcher = page.getByRole('dialog', { name: 'Choose an agent' })
  await expect(switcher).toBeVisible()
  await expect(
    switcher.getByRole('button', { name: /Application and case helper/ }),
  ).toHaveAttribute('aria-current', 'true')
  await page.keyboard.press('Escape')
  await expect(switcher).toHaveCount(0)
  await expect(editor).toHaveValue('Synthetic configured starter')
  await editor.fill('')
  await expect(page.locator('#context-budget')).toHaveCount(0)
  await expect(page.getByText('Not saved', { exact: true })).toHaveCount(0)
  expect(state.requests).toHaveLength(0)
})

test('default helper explains its job and offers example tasks without auto-sending', async ({
  page,
}, testInfo) => {
  const state = await workspace(page, { config: { agents: [guidedReview] } })
  await expect(page.locator('.agent-picker')).toHaveText(
    'Application and case helper',
  )
  await expect(page.locator('.chat-welcome')).not.toContainText(
    'You are using an existing agent, not creating one',
  )
  await expect(page.locator('.chat-welcome .agent-guide')).toContainText(
    guidedReview.guidance!.input,
  )
  await expect(page.locator('.chat-welcome .agent-guide')).toContainText(
    guidedReview.guidance!.output,
  )
  await expect(page.locator('.prompt-options button strong')).toHaveText([
    'Check against a checklist',
    'Summarize case notes',
    'Compare a proposal (preview)',
    'Help me get started',
  ])
  await expect(page.locator('#chat-privacy')).toBeInViewport({ ratio: 1 })
  await illustrativeScreenshot(page, testInfo, 'demo-starters.png', 'sidebar')
  await page.emulateMedia({ colorScheme: 'dark' })
  await illustrativeScreenshot(
    page,
    testInfo,
    'demo-starters-dark.png',
    'sidebar',
  )
  await page.emulateMedia({ colorScheme: 'light' })
  const editor = page.getByRole('textbox', { name: 'Message', exact: true })
  for (const prompt of guidedReview.prompts) {
    await page.getByRole('button', { name: prompt.label, exact: true }).click()
    await expect(editor).toHaveValue(prompt.text)
    await expect(editor).toBeFocused()
    expect(state.requests).toHaveLength(0)
  }
  await openReadyAgents(page)
  await expect(page.locator('.catalog-agent')).toHaveCount(1)
  await expect(
    page.getByRole('heading', {
      name: 'Application and case helper',
      exact: true,
    }),
  ).toBeVisible()
  await page
    .getByRole('button', { name: 'Return to chat', exact: true })
    .click()
  const proposal = guidedReview.prompts[2]
  await page.getByRole('button', { name: proposal.label, exact: true }).click()
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(
    page.getByRole('button', { name: 'Save to shared history' }),
  ).toBeEnabled()
  expect(state.requests).toEqual([
    {
      agent_id: 'customer-review',
      input: proposal.text,
      history: [],
      thread: expect.stringMatching(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
      ),
    },
  ])
  await page.locator('.receipt-details > summary').click()
  await expect(
    page.getByText('Verified receipt', { exact: true }),
  ).toBeVisible()
  await expect(page.locator('.receipt')).toContainText('inspect_application')
  await expect(page.locator('.receipt')).toContainText(
    'application-review-agent',
  )
})

test('handoff timeline shows a verified specialist without opening execution details', async ({
  page,
}, testInfo) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await workspace(page)
  await send(page)
  const timeline = page.getByRole('list', { name: 'Handoff timeline' })
  await expect(timeline).toBeVisible()
  await expect(timeline.getByRole('listitem')).toHaveText([
    'You asked',
    /Application and case helper\s*Coordinator/,
    /application-review-agent\s*Verified/,
    'You check the findings',
  ])
  await expect(page.locator('.receipt-details')).not.toHaveAttribute('open')
  await expect(page.locator('.handoff-timeline')).not.toContainText(/\d/)
  expect(
    await timeline.evaluate(
      (element) =>
        element.getBoundingClientRect().right <= innerWidth &&
        document.documentElement.scrollWidth <= innerWidth &&
        element.getAnimations({ subtree: true }).length === 0,
    ),
  ).toBe(true)
  await timeline.screenshot({
    path: testInfo.outputPath('handoff-timeline.png'),
  })
  await page.emulateMedia({ colorScheme: 'dark' })
  await expect(timeline.getByText('Verified', { exact: true })).toBeVisible()
  await timeline.screenshot({
    path: testInfo.outputPath('handoff-timeline-dark.png'),
  })
})

test('handoff timeline marks unverified receipts', async ({ page }) => {
  await workspace(page, {
    receipts: [
      {
        tool: 'inspect_application',
        call_id: null,
        verified: false,
        agent: null,
        output: null,
      },
    ],
  })
  await send(page)
  const timeline = page.getByRole('list', { name: 'Handoff timeline' })
  await expect(timeline.getByRole('listitem').nth(2)).toHaveText(
    /inspect_application\s*Tool call\s*Unverified/,
  )
  await expect(timeline).not.toContainText('Target not verified')
  await expect(timeline.getByText('Verified', { exact: true })).toHaveCount(0)
})

test('self-targeted lookups on a created agent show tool calls, not a handoff', async ({
  page,
}) => {
  const created = {
    ...agent,
    id: 'created-service-planner',
    label: 'Service request planner',
    agent: 'service-request-planner-1a2b',
    tools: { lookup_demo_request: 'service-request-planner-1a2b' },
  }
  await workspace(page, {
    config: { agents: [created], default_agent: created.id },
    receipts: [
      {
        tool: 'lookup_demo_request',
        call_id: 'call-1',
        verified: true,
        agent: created.agent,
        output: 'Synthetic request record.',
      },
    ],
  })
  await send(page)
  const timeline = page.getByRole('list', { name: 'Handoff timeline' })
  await expect(timeline.getByRole('listitem')).toHaveText([
    'You asked',
    /Service request planner\s*Agent/,
    /lookup_demo_request\s*Tool call\s*Verified/,
    'You check the findings',
  ])
  await expect(timeline).not.toContainText('Coordinator')
  await expect(timeline).not.toContainText(created.agent)
})

test('answers without receipts show no handoff timeline', async ({ page }) => {
  await workspace(page, { receipts: [] })
  await send(page)
  await expect(page.locator('.assistant-message')).toContainText(
    'Section 1 is missing a budget.',
  )
  await expect(
    page.getByRole('list', { name: 'Handoff timeline' }),
  ).toHaveCount(0)
  await expect(page.locator('.receipt-details > summary')).toContainText(
    'Execution details',
  )
})

test('catalog uses customer names while retaining runtime targets and scenario status', async ({
  page,
}) => {
  const state = await workspace(page, { config: { agents: registry } })
  expect(
    registry.map(({ id, agent, tools }) => ({ id, agent, tools })),
  ).toEqual([
    {
      id: 'customer-review',
      agent: 'customer-review-coordinator',
      tools: {
        inspect_application: 'application-review-agent',
        inspect_case: 'case-review-agent',
      },
    },
    {
      id: 'review-coordinator',
      agent: 'review-coordinator-agent',
      tools: {
        review_application: 'application-review-agent',
        review_case: 'case-review-agent',
      },
    },
    { id: 'application-review', agent: 'application-review-agent', tools: {} },
    { id: 'case-review', agent: 'case-review-agent', tools: {} },
  ])
  await openReadyAgents(page)
  await expect(page.locator('.catalog-agent h2')).toHaveText([
    'Application and case helper',
    'Application and case helper (base setup)',
    'Application checker',
    'Case notes summarizer',
  ])
  await expect(page.locator('.category-label')).toHaveText([
    'Coordinator: hands off to specialists',
    'Coordinator: developer variant',
    'Specialist: works on its own',
    'Specialist: works on its own',
  ])
  await expect(page.locator('.catalog-paths strong')).toHaveText([
    'Use an agent',
    'Create your own',
    'Repository drafts',
  ])
  await page.locator('.catalog-status > summary').click()
  await expect(page.locator('.catalog-status')).toContainText(
    'Automated tests use simulated responses, so check live answers yourself.',
  )
  await expect(page.locator('.catalog-status')).toContainText(
    'Comparing proposals with requirements is in preview',
  )
  await expect(page.locator('.catalog-status')).not.toContainText('PLANNED')
  await expect(page.locator('.catalog-status')).toContainText(
    "They aren't an official Microsoft product.",
  )
  await expect(
    page.locator('.catalog-agent').filter({
      has: page.getByRole('heading', {
        name: 'Application and case helper (base setup)',
        exact: true,
      }),
    }),
  ).toContainText('it does not add capabilities')
  for (const item of registry) {
    const card = page.locator('.catalog-agent').filter({
      has: page.getByRole('heading', { name: item.label, exact: true }),
    })
    for (const field of ['input', 'output'] as const)
      await expect(card.locator('.agent-guide')).toContainText(
        item.guidance![field],
      )
    await expect(card.locator('.catalog-human-decision')).toContainText(
      item.guidance!.limits,
    )
    const details = card.locator('.catalog-runtime')
    await expect(details.locator('dl')).toBeHidden()
    await details.locator('summary').click()
    await expect(details).toContainText(item.guidance!.delegation)
    await expect(details.locator('dd')).toHaveText([item.id, item.agent])
    await expect(details).toContainText(
      `${Object.keys(item.tools).length} tool bindings`,
    )
    for (const [tool, target] of Object.entries(item.tools)) {
      await expect(details.locator('li').filter({ hasText: tool })).toHaveText(
        `${tool} to ${target}`,
      )
    }
    await expect(details).toContainText(
      'Configured targets, not execution proof.',
    )
    await expect(details).toContainText('stored receipts are not reverified.')
    await expect(details).toContainText(item.guidance!.configuration)
    await expect(details).toContainText(
      "Editing it does not change a deployed agent's instructions or tools.",
    )
  }
  await page.getByRole('textbox', { name: 'Search agents' }).fill('case notes')
  await expect(page.locator('.catalog-agent h2')).toHaveText([
    'Application and case helper',
    'Case notes summarizer',
  ])
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  expect(state.requests).toHaveLength(0)
})

test('agent guidance remains inspectable without reconfiguring the runtime', async ({
  page,
}, testInfo) => {
  const state = await workspace(page)
  const summary = page.locator('.agent-about > summary')
  const guide = page.getByRole('complementary', {
    name: 'Selected agent guide',
  })
  await expect(guide).toBeHidden()
  await summary.click()
  await expect(guide).toBeVisible()
  await expect(guide).toContainText(
    'Your message gives it a task; it does not change its tools or permanent instructions',
  )
  for (const field of ['input', 'output', 'limits', 'delegation'] as const)
    await expect(guide).toContainText(agent.guidance![field])
  expect(
    await guide.evaluate((element) => {
      const { left, right, top, bottom } = element.getBoundingClientRect()
      return (
        left >= 0 && right <= innerWidth && top >= 0 && bottom <= innerHeight
      )
    }),
  ).toBe(true)
  expect(state.requests).toHaveLength(0)
  await illustrativeScreenshot(page, testInfo, 'agent-guide.png')
  await summary.focus()
  await summary.press('Escape')
  await expect(guide).toBeHidden()
  await send(page)
  await summary.click()
  await expect(guide).toContainText(agent.guidance!.output)
  expect(state.requests).toHaveLength(1)
})

test('configuration guidance separates UI settings from deployed agent behavior', async ({
  page,
}, testInfo) => {
  const state = await workspace(page)
  await openReadyAgents(page)
  const guide = page.locator('.configuration-guide')
  await guide.locator(':scope > summary').click()
  await expect(guide).toContainText(
    "Agent creation isn't turned on in this Lab",
  )
  await expect(guide).toContainText(
    'A starter is just an example task and message, not a new agent',
  )
  await expect(guide.locator('.configuration-sources dl')).toBeHidden()
  await guide.locator('.configuration-sources > summary').click()
  await expect(guide).toContainText('workbench\\agents.json')
  await expect(guide).toContainText('rebuild and redeploy the Lab')
  await expect(guide).toContainText('publish and test a new agent version')
  await expect(guide).toContainText('they do not register runtime tools')
  for (const setting of [
    'visible_agents',
    'default_agent',
    'workspace_title',
    'WORKBENCH_VISIBLE_AGENTS',
    'WORKBENCH_DEFAULT_AGENT',
    'WORKBENCH_TITLE',
  ])
    await expect(
      guide.locator('code').filter({ hasText: new RegExp(`^${setting}$`) }),
    ).toBeVisible()
  await expect(page.getByRole('textbox')).toHaveCount(1)
  await expect(page.locator('.catalog-agent')).toHaveCount(1)
  if (testInfo.project.name === 'desktop')
    expect(
      (await page.locator('.catalog-agent').boundingBox())!.width,
    ).toBeGreaterThanOrEqual(500)
  await illustrativeScreenshot(page, testInfo, 'configuration-guide.png')
  expect(state.requests).toHaveLength(0)
})

test('legacy catalogs without guidance remain usable without invented capabilities', async ({
  page,
}) => {
  await workspace(page, {
    config: { agents: [{ ...agent, guidance: undefined }] },
  })
  await expect(page.locator('.chat-welcome')).toContainText(
    'This agent has no getting-started guide',
  )
  await expect(
    page.getByRole('button', {
      name: 'Check against a checklist',
      exact: true,
    }),
  ).toBeEnabled()
})

test('guidance accepts the server limit of 1200 Unicode characters', async ({
  page,
}) => {
  const input = '\u{1F600}'.repeat(1200)
  await workspace(page, {
    config: { agents: [{ ...agent, guidance: { ...agent.guidance!, input } }] },
  })
  await expect(page.locator('.chat-welcome .agent-guide')).toContainText(input)
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('shared lab details are available on demand across workspace views', async ({
  page,
}, testInfo) => {
  await workspace(page, { config: { reviews_enabled: true } })
  const control = page.getByTitle('About this shared lab', { exact: true })
  const notice = page.getByRole('complementary', { name: 'Shared lab details' })
  for (const name of ['Chat', 'Shared history', 'All agents', 'Performance']) {
    await page
      .getByRole('navigation', { name: 'Workspace' })
      .getByTitle(name, { exact: true })
      .click()
    // The top bar names the page only in its breadcrumb, never as a title.
    await expect(
      page
        .getByRole('banner')
        .getByText(name, { exact: true })
        .and(page.locator(':not(.topbar-crumbs *)')),
    ).toHaveCount(0)
    await expect(control).toBeInViewport()
    await expect(notice).toBeHidden()
    await expect(
      page.getByRole('complementary', { name: 'Lab data boundary' }),
    ).toHaveCount(0)
    await control.click()
    await expect(notice).toBeInViewport()
    await expect(notice).toContainText(
      'No user sign-in. Saved records are shared.',
    )
    await expect(notice).toContainText('Use sample data only.')
    await expect(notice).toContainText(
      'read, modify and delete saved chats, and read reviews and add requested evidence',
    )
    expect(
      await notice.evaluate((element) => {
        const { left, right } = element.getBoundingClientRect()
        return left >= 0 && right <= innerWidth
      }),
    ).toBe(true)
    if (name === 'Chat') {
      await page.evaluate(() => document.fonts.ready)
      await page.screenshot({
        path: testInfo.outputPath('shared-lab-details.png'),
      })
      await control.press('Enter')
      await expect(notice).toBeHidden()
      await control.press('Space')
      await expect(notice).toBeVisible()
    }
  }
})

test('shared lab details fit narrow screens and close with Escape', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 720 })
  await workspace(page, {
    config: {
      agents: [
        {
          ...agent,
          label: 'Customer application and supporting evidence review',
        },
      ],
    },
  })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  await expect(
    page.getByRole('complementary', { name: 'Lab data boundary' }),
  ).toHaveCount(0)
  await expect(
    page.getByRole('button', {
      name: 'Customer application and supporting evidence review',
    }),
  ).toBeInViewport()
  const control = page.getByTitle('About this shared lab', { exact: true })
  const notice = page.getByRole('complementary', { name: 'Shared lab details' })
  await control.focus()
  await control.press('Enter')
  await expect(notice).toBeInViewport()
  expect(
    await notice.evaluate((element) => {
      const { left, right } = element.getBoundingClientRect()
      return left >= 0 && right <= innerWidth
    }),
  ).toBe(true)
  await control.press('Escape')
  await expect(notice).toBeHidden()
  await expect(control).toBeFocused()
})

test('disconnected preview does not claim connected shared storage', async ({
  page,
}) => {
  await workspace(page, { preview: true })
  await expect(
    page.getByTitle('About this shared lab', { exact: true }),
  ).toHaveCount(0)
  await expect(
    page.getByRole('complementary', { name: 'Shared lab details' }),
  ).toHaveCount(0)
  await expect(page.getByText('Local preview', { exact: true })).toBeVisible()
  await expect(page.locator('.chat-welcome .welcome-hint')).toContainText(
    'No model calls or saved records',
  )
  await expect(
    page.getByRole('complementary', { name: 'Lab data boundary' }),
  ).toHaveCount(0)
})

test('save, reopen, follow up, update and delete shared history', async ({
  page,
}) => {
  const state = await workspace(page)
  await send(page)
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect(page.getByText('Saved / shared', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'New chat', exact: true }).click()
  await page
    .getByRole('button', { name: 'Shared history', exact: true })
    .click()
  await page.locator('.saved-open').click()
  const storedTimeline = page.getByRole('list', { name: 'Handoff timeline' })
  await expect(storedTimeline.getByRole('listitem').nth(2)).toHaveText(
    /application-review-agent\s*Stored \/ not reverified/,
  )
  await expect(
    storedTimeline.getByText('Verified', { exact: true }),
  ).toHaveCount(0)
  await page.locator('.receipt-details > summary').click()
  await expect(
    page.locator('.receipt').getByText('Stored / not reverified'),
  ).toBeVisible()
  await expect(page.getByText('Verified receipt', { exact: true })).toHaveCount(
    0,
  )
  await send(page, 'What evidence is missing?')
  expect(state.requests[1].history.map((message) => message.role)).toEqual([
    'user',
    'assistant',
  ])
  expect(state.requests[1].thread).not.toBe(state.requests[0].thread)
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect(page.getByText('Saved / shared', { exact: true })).toBeVisible()
  expect(state.updates).toEqual(['v1'])
  expect(state.saves[1].turns.every((turn) => !('stored' in turn))).toBeTruthy()
  await page.getByRole('button', { name: 'New chat', exact: true }).click()
  await page
    .getByRole('button', { name: 'Shared history', exact: true })
    .click()
  page.once('dialog', (dialog) => dialog.accept())
  await page
    .getByRole('button', { name: 'Delete Review synthetic APP-1' })
    .click()
  await expect(page.getByText('No saved conversations')).toBeVisible()
  expect(state.deletes).toEqual(['v2'])
})

test('conflicting save preserves local replies and allows export', async ({
  page,
}) => {
  const state = await workspace(page, { conflict: true })
  await send(page)
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect(page.getByText('Saved / shared', { exact: true })).toBeVisible()
  await send(page, 'Keep this local follow-up')
  expect(state.requests[1].thread).toBe(state.requests[0].thread)
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect(page.getByRole('status')).toContainText(
    'changed in another browser',
  )
  await expect(
    page.getByText('Keep this local follow-up', { exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Export conversation' }),
  ).toBeEnabled()
  await expect(page.getByText('Unsaved changes', { exact: true })).toBeVisible()
})

test('history timeout releases controls without losing the draft', async ({
  page,
}) => {
  await page.clock.install()
  await workspace(page, { stalledHistory: true })
  await page.getByRole('textbox', { name: 'Message' }).fill('Keep this draft')
  await page
    .getByRole('button', { name: 'Shared history', exact: true })
    .click()
  await expect(page.getByText('Loading history...')).toBeVisible()
  await page.clock.runFor(45001)
  await expect(page.getByRole('status')).toContainText(
    'History request stopped',
  )
  await page.getByRole('button', { name: 'Chat', exact: true }).click()
  await expect(page.getByRole('textbox', { name: 'Message' })).toHaveValue(
    'Keep this draft',
  )
  await expect(page.getByRole('button', { name: 'Send message' })).toBeEnabled()
})

test('draft export includes unsent text and reload warns', async ({ page }) => {
  await workspace(page)
  const editor = page.getByRole('textbox', { name: 'Message' })
  await editor.fill('Unsent synthetic draft')
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export conversation' }).click()
  const download = await downloadPromise
  const payload = JSON.parse(await readFile((await download.path())!, 'utf8'))
  expect(payload.draft).toBe('Unsent synthetic draft')
  const dialogPromise = page.waitForEvent('dialog')
  void page.reload().catch(() => null)
  const dialog = await dialogPromise
  expect(dialog.type()).toBe('beforeunload')
  await dialog.dismiss()
  await expect(editor).toHaveValue('Unsent synthetic draft')
})

test('stop waiting does not automatically retry', async ({ page }) => {
  const state = await workspace(page, { stalledReview: true })
  await page.getByRole('textbox', { name: 'Message' }).fill('Synthetic request')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => state.requests.length).toBe(1)
  await page.getByRole('button', { name: 'Stop waiting' }).click()
  await expect(page.getByRole('alert')).toContainText('Stopped waiting')
  await expect(page.getByRole('textbox', { name: 'Message' })).toHaveValue(
    'Synthetic request',
  )
  expect(state.requests).toHaveLength(1)
})

test('non-JSON gateway errors show the standard failure message', async ({
  page,
}) => {
  const state = await workspace(page, { gatewayError: true })
  await page.getByRole('textbox', { name: 'Message' }).fill('Synthetic request')
  await page.getByRole('button', { name: 'Send message' }).click()
  const alert = page.getByRole('alert')
  await expect(alert).toContainText('Request failed.')
  await expect(alert).not.toContainText(/JSON|token/i)
  await expect(page.getByRole('textbox', { name: 'Message' })).toHaveValue(
    'Synthetic request',
  )
  expect(state.requests).toHaveLength(1)
})

test('UTF-8 byte limit prevents an oversized request', async ({ page }) => {
  const state = await workspace(page)
  await page
    .getByRole('textbox', { name: 'Message' })
    .fill('\u20ac'.repeat(22000))
  await expect(
    page.getByRole('button', { name: 'Send message' }),
  ).toBeDisabled()
  await expect(page.getByRole('alert')).toContainText(
    'Request byte limit exceeded',
  )
  expect(state.requests).toHaveLength(0)
})

test('preview calls do not count as live performance', async ({ page }) => {
  await workspace(page, { preview: true })
  await page
    .getByRole('textbox', { name: 'Message' })
    .fill('Synthetic preview request')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.getByRole('alert')).toContainText('No agent was invoked')
  await page.getByRole('button', { name: 'Performance', exact: true }).click()
  await expect(page.locator('.metric-strip > div').first()).toContainText('0')
})

test('replies show reported tokens and Performance estimates cost from user rates', async ({
  page,
}) => {
  const state = await workspace(page, {
    usage: {
      input_tokens: 1200,
      output_tokens: 300,
      total_tokens: 1500,
      cached_tokens: 200,
      reasoning_tokens: 120,
    },
  })
  await page.evaluate(() => localStorage.removeItem('foundry-lab-token-rates'))
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Review the fictional application')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.assistant-heading')).toContainText(
    '1.0s · 1,500 tokens',
  )
  await page.locator('.receipt-details > summary').click()
  await expect(page.locator('.usage-detail')).toContainText(
    '1,200 in (200 cached) · 300 out (120 reasoning) · 1,500 total',
  )
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect.poll(() => state.saves.length).toBe(1)
  expect(state.saves[0].turns[0].result.usage?.total_tokens).toBe(1500)

  const nav = page.getByRole('navigation', { name: 'Workspace' })
  await nav.getByRole('button', { name: /^Request log/ }).click()
  await expect(
    page.getByRole('table', { name: 'Request log' }).locator('tbody td').nth(4),
  ).toHaveText('1,500 tokens')
  await nav.getByRole('button', { name: 'Performance', exact: true }).click()
  const cost = page.getByRole('region', { name: 'Token usage and cost' })
  await expect(cost.locator('.metric-strip > div')).toHaveText([
    /Input tokens\s*1,200/,
    /Output tokens\s*300/,
    /Estimated cost\s*Add your rates/,
  ])
  await expect(
    page.getByRole('table', { name: 'Benchmark by agent' }),
  ).toContainText('1,500')
  await cost.getByLabel('Input rate per 1M tokens').fill('2')
  await cost.getByLabel('Output rate per 1M tokens').fill('8')
  await cost.getByRole('button', { name: 'Use rates' }).click()
  // 1,200 x 2 / 1M + 300 x 8 / 1M
  await expect(cost.locator('.metric-strip > div').nth(2)).toContainText(
    '0.0048',
  )
  await page.reload()
  await nav.getByRole('button', { name: 'Performance', exact: true }).click()
  await expect(cost.getByLabel('Input rate per 1M tokens')).toHaveValue('2')
  await cost.getByRole('button', { name: 'Clear' }).click()
  expect(
    await page.evaluate(() => localStorage.getItem('foundry-lab-token-rates')),
  ).toBeNull()
  await expect(cost.locator('#budget-alert-status')).toContainText(
    'budget alerts aren’t set up for this Lab',
  )
})

test('Performance says when an Azure budget alerts on Lab spend', async ({
  page,
}) => {
  await workspace(page, { config: { budget_alerts: true } })
  await page
    .getByRole('navigation', { name: 'Workspace' })
    .getByRole('button', { name: 'Performance', exact: true })
    .click()
  const status = page.locator('#budget-alert-status')
  await expect(status).toContainText('50%, 80% and 100%')
  await expect(status).not.toContainText('aren’t set up')
})

test('replies without reported tokens say so instead of showing zero', async ({
  page,
}) => {
  await workspace(page, { usage: null })
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Review the fictional application')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.assistant-heading')).toContainText(
    'Tokens not reported',
  )
  await page
    .getByRole('navigation', { name: 'Workspace' })
    .getByRole('button', { name: 'Performance', exact: true })
    .click()
  await expect(
    page.getByRole('region', { name: 'Token usage and cost' }),
  ).toContainText('1 did not report tokens and are not counted')
})

test('layout, text contrast and reduced motion', async ({ page }, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await workspace(page)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.evaluate(() => document.fonts.ready)
  const geometry = await page.evaluate(() => ({
    overflow: document.documentElement.scrollWidth > innerWidth,
    editor: document
      .querySelector('textarea')!
      .getBoundingClientRect()
      .toJSON(),
    height: innerHeight,
    width: innerWidth,
    animations: document
      .getAnimations()
      .filter((animation) => animation.playState === 'running').length,
  }))
  expect(geometry.overflow).toBeFalsy()
  expect(geometry.editor.bottom).toBeLessThanOrEqual(geometry.height)
  expect(geometry.editor.right).toBeLessThanOrEqual(geometry.width)
  expect(geometry.animations).toBe(0)
  const contrast = await page
    .locator('.composer-toolbar > span')
    .evaluate((element) => {
      const channels = getComputedStyle(element)
        .color.match(/[\d.]+/g)!
        .slice(0, 3)
        .map(Number)
        .map((value) => {
          const normalized = value / 255
          return normalized <= 0.04045
            ? normalized / 12.92
            : ((normalized + 0.055) / 1.055) ** 2.4
        })
      return (
        1.05 /
        (channels[0] * 0.2126 +
          channels[1] * 0.7152 +
          channels[2] * 0.0722 +
          0.05)
      )
    })
  expect(contrast).toBeGreaterThanOrEqual(4.5)
  expect(errors).toEqual([])
  await page.screenshot({ path: testInfo.outputPath('workspace.png') })
})

test('startup timeout preserves a draft and supports explicit retry', async ({
  page,
}, testInfo) => {
  await page.clock.install()
  const state = await workspace(page, { startup: 'stalled' })
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Keep my synthetic draft')
  await expect(
    page.getByRole('button', { name: 'Send message' }),
  ).toBeDisabled()
  await page.clock.runFor(15001)
  await expect(page.getByRole('alert')).toContainText('configuration timed out')
  await page.screenshot({ path: testInfo.outputPath('startup-recovery.png') })
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Send message' })).toBeEnabled()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue('Keep my synthetic draft')
  expect(state.configRequests).toBe(2)
  expect(state.requests).toHaveLength(0)
})

for (const startup of ['invalid', 'invalid-guidance', 'failed'] as const) {
  test(`${startup} startup configuration fails closed and recovers`, async ({
    page,
  }) => {
    const state = await workspace(page, { startup })
    await expect(page.getByRole('alert')).toContainText(
      'configuration unavailable or invalid',
    )
    await expect(
      page.getByRole('button', { name: 'Send message' }),
    ).toBeDisabled()
    await page.getByRole('button', { name: 'Retry', exact: true }).click()
    await expect(
      page.getByRole('button', { name: 'Check against a checklist' }),
    ).toBeVisible()
    expect(state.configRequests).toBe(2)
  })
}

test('configured title, default agent, prompts and character limits drive the UI', async ({
  page,
}) => {
  const specialist = {
    ...agent,
    id: 'case-review',
    label: 'Casework assistance',
    prompts: [{ label: 'Check a date', text: 'CASE-1' }],
  }
  const state = await workspace(page, {
    config: {
      title: 'AI Foundry Test Lab',
      agents: [agent, specialist],
      default_agent: specialist.id,
      max_characters: 6,
    },
  })
  await expect(page).toHaveTitle('AI Foundry Test Lab')
  await page.getByRole('button', { name: 'Check a date' }).click()
  const editor = page.getByRole('textbox', { name: 'Message', exact: true })
  await expect(editor).toHaveValue('CASE-1')
  await expect(page.getByRole('button', { name: 'Send message' })).toBeEnabled()
  await editor.fill('\u{1F600}'.repeat(6))
  await expect(page.getByRole('button', { name: 'Send message' })).toBeEnabled()
  await editor.fill('CASE-12')
  await expect(page.getByRole('alert')).toContainText(
    'Character limit exceeded',
  )
  await expect(
    page.getByRole('button', { name: 'Send message' }),
  ).toBeDisabled()
  expect(state.requests).toHaveLength(0)
})

test('review deadline is distinct from Stop and does not retry', async ({
  page,
}) => {
  await page.clock.install()
  const state = await workspace(page, {
    stalledReview: true,
    config: { review_timeout_ms: 5000 },
  })
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Synthetic review')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => state.requests.length).toBe(1)
  await page.clock.runFor(5001)
  await expect(page.getByRole('alert')).toContainText('Request timed out')
  await expect(page.getByRole('button', { name: 'Send message' })).toBeEnabled()
  await page.getByRole('button', { name: 'Performance', exact: true }).click()
  await expect(
    page.getByRole('cell', { name: 'timed-out', exact: true }),
  ).toBeVisible()
  expect(state.requests).toHaveLength(1)
})

test('continuation previews context and leaves saved source unchanged', async ({
  page,
}, testInfo) => {
  const state = await workspace(page, { config: { max_history_turns: 0 } })
  await send(page)
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect(page.getByText('Saved / shared', { exact: true })).toBeVisible()
  const source = JSON.stringify(state.document)
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Next synthetic question')
  await expect(page.getByRole('alert')).toContainText(
    'Conversation turn limit reached',
  )
  await page.getByRole('button', { name: 'Continue in new chat' }).click()
  const dialog = page.getByRole('dialog', { name: 'Continue in new chat' })
  await expect(dialog).toBeVisible()
  await expect(
    dialog.getByRole('textbox', { name: 'Carry-over draft' }),
  ).toContainText('Previous reply (unverified context)')
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue('Next synthetic question')
  await page.getByRole('button', { name: 'Continue in new chat' }).click()
  await dialog
    .getByRole('textbox', { name: 'Carry-over draft' })
    .fill('Reviewed carry-over context')
  await page.screenshot({ path: testInfo.outputPath('continuation.png') })
  await dialog
    .getByRole('button', { name: 'Start new chat', exact: true })
    .click()
  await expect(dialog).not.toBeVisible()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue('Reviewed carry-over context')
  await expect(page.getByRole('button', { name: 'Send message' })).toBeEnabled()
  expect(state.requests).toHaveLength(1)
  expect(JSON.stringify(state.document)).toBe(source)
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => state.requests.length).toBe(2)
  expect(state.requests[1].history).toEqual([])
  expect(state.requests[1].thread).not.toBe(state.requests[0].thread)
})

test('composer grows within viewport bounds and shrinks again', async ({
  page,
}, testInfo) => {
  await workspace(page)
  const editor = page.getByRole('textbox', { name: 'Message', exact: true })
  const initial = (await editor.boundingBox())!
  await editor.fill('Synthetic evidence line\n'.repeat(25))
  const grown = (await editor.boundingBox())!
  expect(grown.height).toBeGreaterThan(initial.height)
  expect(grown.height).toBeLessThanOrEqual(240)
  expect(grown.y + grown.height).toBeLessThan(page.viewportSize()!.height)
  await expect(
    page.getByRole('button', { name: 'Send message' }),
  ).toBeInViewport()
  await page.screenshot({ path: testInfo.outputPath('expanded-composer.png') })
  await editor.fill('Short draft')
  expect((await editor.boundingBox())!.height).toBeLessThan(grown.height)
})
