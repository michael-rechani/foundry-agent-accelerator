import { expect, test, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import type { Turn } from '../src/conversation-types'
import type { Config } from '../src/workspace-config'

const agent = {
  id: 'customer-review',
  label: 'Customer review',
  category: 'Coordinator',
  description: 'Profile-driven application and case review',
  agent: 'customer-review-coordinator',
  tools: { inspect_application: 'application-review-agent' },
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
    preview?: boolean
    startup?: 'stalled' | 'invalid' | 'failed'
    config?: Partial<Config>
  } = {},
) {
  const config: Config = {
    title: 'AI Foundry Lab',
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
        if (options.startup === 'failed')
          return respond({ error: 'unavailable' }, 503)
      }
      return respond(config)
    }
    if (path === '/api/reviews') {
      state.requests.push(request.postDataJSON())
      if (options.stalledReview) return
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
  await page.goto('/')
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

for (const startup of ['invalid', 'failed'] as const) {
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
    label: 'Case specialist',
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
