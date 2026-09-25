import { expect, test, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import type { Turn } from '../src/conversation-types'
import type { Config } from '../src/workspace-config'
import { guidedReview, illustrativeScreenshot, registry } from './fixtures'
const agent = {
  ...guidedReview,
  prompts: [
    { label: 'Review an application', text: 'Synthetic configured starter' },
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
    requests: [] as { history: { role: string; content: string }[] }[],
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
        agent: agent.agent,
        text: 'APP-1 is missing a budget.',
        elapsed_ms: 1000,
        receipts: [
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

test('chat starts with focused controls and preserves drafts when choosing an agent', async ({
  page,
}) => {
  const state = await workspace(page)
  await expect(
    page.getByRole('heading', {
      name: 'Use Application and case helper',
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
    .getByRole('button', { name: 'Review an application', exact: true })
    .click()
  const editor = page.getByRole('textbox', { name: 'Message', exact: true })
  await expect(editor).toHaveValue('Synthetic configured starter')
  await expect(editor).toBeFocused()
  await expect(page.getByText('Not saved', { exact: true })).toBeVisible()
  await expect(page.locator('#context-budget summary')).toContainText(
    'Conversation limits',
  )

  await page
    .getByRole('banner')
    .getByTitle('Choose an agent', { exact: true })
    .click()
  await expect(
    page.getByRole('heading', { name: 'Choose an agent', exact: true }),
  ).toBeVisible()
  await page
    .getByRole('button', { name: 'Return to chat', exact: true })
    .click()
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
  await expect(page.locator('.chat-welcome')).toContainText(
    'You are using an existing agent, not creating one',
  )
  await expect(page.locator('.chat-welcome .agent-guide')).toContainText(
    guidedReview.guidance!.input,
  )
  await expect(page.locator('.chat-welcome .agent-guide')).toContainText(
    guidedReview.guidance!.output,
  )
  await expect(page.locator('.prompt-options button')).toHaveText([
    'Review an application',
    'Summarize case notes',
    'Compare a proposal (preview)',
    'Help me get started',
  ])
  await illustrativeScreenshot(page, testInfo, 'demo-starters.png')
  await page.emulateMedia({ colorScheme: 'dark' })
  await illustrativeScreenshot(page, testInfo, 'demo-starters-dark.png')
  await page.emulateMedia({ colorScheme: 'light' })
  const editor = page.getByRole('textbox', { name: 'Message', exact: true })
  for (const prompt of guidedReview.prompts) {
    await page.getByRole('button', { name: prompt.label, exact: true }).click()
    await expect(editor).toHaveValue(prompt.text)
    await expect(editor).toBeFocused()
    expect(state.requests).toHaveLength(0)
  }
  await page
    .getByRole('banner')
    .getByTitle('Choose an agent', { exact: true })
    .click()
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
    { agent_id: 'customer-review', input: proposal.text, history: [] },
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
  await page
    .getByRole('banner')
    .getByTitle('Choose an agent', { exact: true })
    .click()
  await expect(page.locator('.catalog-agent h2')).toHaveText([
    'Application and case helper',
    'Application and case helper (base setup)',
    'Application checker',
    'Case notes summarizer',
  ])
  await expect(page.locator('.category-label')).toHaveText([
    'Uses specialist agents',
    'Alternate setup',
    'Single specialist',
    'Single specialist',
  ])
  await page.locator('.catalog-status > summary').click()
  await expect(page.locator('.catalog-status')).toContainText(
    'Automated tests use simulated responses, so check live answers yourself.',
  )
  await expect(page.locator('.catalog-status')).toContainText(
    'Requirements and proposal review is in preview',
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
  ).toContainText('not an extra planning capability')
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
  await page.getByTitle('Choose an agent', { exact: true }).click()
  const guide = page.locator('.configuration-guide')
  await guide.locator(':scope > summary').click()
  await expect(guide).toContainText(
    'This server does not advertise agent creation',
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
    page.getByRole('button', { name: 'Review an application', exact: true }),
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
  for (const name of [
    'Chat',
    'Document reviews',
    'Shared history',
    'Agent catalog',
    'Performance',
  ]) {
    await page
      .getByRole('navigation', { name: 'Workspace' })
      .getByTitle(name, { exact: true })
      .click()
    await expect(
      page.getByRole('banner').getByText(name, { exact: true }),
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
    await expect(notice).toContainText('Use synthetic data only.')
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
  await expect(page.locator('.preview-explanation')).toContainText(
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
  await page.locator('.receipt-details > summary').click()
  await expect(page.getByText('Stored / not reverified')).toBeVisible()
  await expect(page.getByText('Verified receipt', { exact: true })).toHaveCount(
    0,
  )
  await send(page, 'What evidence is missing?')
  expect(state.requests[1].history.map((message) => message.role)).toEqual([
    'user',
    'assistant',
  ])
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
  await workspace(page, { conflict: true })
  await send(page)
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect(page.getByText('Saved / shared', { exact: true })).toBeVisible()
  await send(page, 'Keep this local follow-up')
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
      page.getByRole('button', { name: 'Review an application' }),
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
