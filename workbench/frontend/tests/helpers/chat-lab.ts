import { type Page, expect } from '@playwright/test'
import { guidedReview } from '../fixtures'
import { labConfig, modeFor } from './lab-config'
import { mockApi } from './mock-api'
import { workspaceNav } from './navigation'
import { type Receipt, type Turn } from '../../src/conversation-types'
import { type Config } from '../../src/workspace-config'

export const agent = {
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
export type HealthReply = { status?: number; body?: unknown; html?: boolean }
export const healthy: HealthReply = {
  body: { status: 'ready', foundry: 'ready', cosmos: 'ready' },
}

export async function openWorkspace(
  page: Page,
  options: {
    // One reply for every check, or one per check with the last repeated.
    health?: HealthReply | HealthReply[]
    conflict?: boolean
    stalledHistory?: boolean
    stalledReview?: boolean
    busyReview?: boolean
    gatewayError?: boolean
    preview?: boolean
    startup?: 'stalled' | 'invalid' | 'invalid-guidance' | 'failed'
    config?: Partial<Config>
    receipts?: Receipt[]
    usage?: unknown
    answer?: string
    answers?: string[]
  } = {},
) {
  const config = labConfig({
    mode: modeFor(options.preview),
    agents: [agent],
    default_agent: agent.id,
    history_enabled: !options.preview,
    ...options.config,
  })
  const state = {
    configRequests: 0,
    healthRequests: 0,
    document: null as Document | null,
    requests: [] as {
      history: { role: string; content: string }[]
      thread: string
    }[],
    saves: [] as { turns: Turn[] }[],
    updates: [] as string[],
    deletes: [] as string[],
  }
  await mockApi(page, async ({ route, request, path, respond }) => {
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
    if (path === '/api/health/dependencies') {
      state.healthRequests++
      const replies = [options.health ?? healthy].flat()
      const reply = replies[Math.min(state.healthRequests, replies.length) - 1]
      if (reply.html)
        return route.fulfill({
          status: reply.status ?? 502,
          contentType: 'text/html',
          body: '<html><body>Bad Gateway</body></html>',
        })
      return respond(reply.body, reply.status ?? 200)
    }
    if (path === '/api/reviews') {
      state.requests.push(request.postDataJSON())
      if (options.stalledReview) return
      if (options.busyReview)
        return route.fulfill({
          status: 429,
          headers: { 'Retry-After': '12' },
          json: { error: 'busy', request_id: 'request-busy' },
        })
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
        text:
          options.answers?.[state.requests.length - 1] ??
          options.answer ??
          'Section 1 is missing a budget.',
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

export async function send(page: Page, text = 'Review synthetic APP-1') {
  await page.getByRole('textbox', { name: 'Message' }).fill(text)
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(
    page.getByRole('button', { name: 'Save to shared history' }),
  ).toBeEnabled()
}

export async function openOverview(page: Page) {
  await workspaceNav(page)
    .getByRole('button', { name: 'Overview', exact: true })
    .click()
  await expect(
    page.getByRole('heading', { level: 1, name: 'Operations' }),
  ).toBeVisible()
}

export const serviceStatus = (page: Page, service: string) =>
  page
    .locator('.operations-services tbody tr')
    .filter({
      has: page.getByRole('rowheader', { name: service, exact: true }),
    })
    .locator('.operations-status')

export const labStatus = (page: Page) =>
  page.locator('.metric-strip-4 > div').first().locator('strong')

export const openSteps = async (page: Page) => {
  const panel = page.locator('.answer-steps').last()
  await panel.locator('summary').click()
  return panel.getByRole('list', { name: 'How I got this' })
}
