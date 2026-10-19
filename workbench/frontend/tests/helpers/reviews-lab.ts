import { type Page, expect } from '@playwright/test'
import { guidedReview } from '../fixtures'
import { labConfig, modeFor } from './lab-config'
import { mockApi } from './mock-api'
import { workspaceNav } from './navigation'
import { type Review } from '../../src/review-client'
import { type Agent } from '../../src/workspace-config'

export async function openReviews(
  page: Page,
  preview = false,
  agents: Agent[] = [guidedReview],
) {
  const state = {
    document: null as Review | null,
    executions: 0,
    recoveries: 0,
    conflict: false,
    pollFailure: null as 'network' | 'rate-limit' | null,
    runningReads: 0,
    chatRequests: 0,
    creations: [] as Pick<
      Review,
      'title' | 'agent_id' | 'criteria' | 'evidence'
    >[],
  }
  await mockApi(page, async ({ route, request, path, respond }) => {
    if (path === '/api/config')
      return respond(
        labConfig({
          mode: modeFor(preview),
          reviews_enabled: !preview,
          history_enabled: !preview,
          default_agent: 'customer-review',
          agents,
        }),
      )
    if (path === '/api/review-runs' && request.method() === 'POST') {
      state.creations.push(request.postDataJSON())
      state.document = {
        ...request.postDataJSON(),
        id: 'review-12345678-1234-1234-1234-123456789abc',
        status: 'draft',
        runs: [],
        _etag: '1',
        updated_at: '2026-09-06T00:00:00Z',
      }
      return route.fulfill({ status: 201, json: state.document })
    }
    if (path === '/api/review-runs')
      return route.fulfill({
        json: { items: state.document ? [state.document] : [], cursor: null },
      })
    if (path === '/api/reviews') {
      state.chatRequests++
      return route.fulfill({
        status: 400,
        json: { error: 'unexpected_chat_request' },
      })
    }
    const document = state.document
    if (!document)
      return route.fulfill({ status: 404, json: { error: 'not_found' } })
    if (path.endsWith('/execute') || path.endsWith('/resume')) {
      const recovering = path.endsWith('/resume')
      if (state.conflict)
        return route.fulfill({ status: 409, json: { error: 'review_changed' } })
      expect(request.headers()['if-match']).toBe(document._etag)
      const previous = document.runs.at(-1)
      if (recovering) {
        expect(request.postDataJSON()).toEqual({ confirm_cost: true })
        expect(document.status).toBe('interrupted')
        expect(document.runs.length).toBeLessThan(4)
        state.recoveries++
      }
      state.executions++
      document.status = 'running'
      document._etag = String(Number(document._etag) + 1)
      document.runs.push({
        id: 'run-' + state.executions,
        started_at: document.updated_at,
        input: recovering
          ? structuredClone(previous!.input)
          : {
              criteria: [...document.criteria],
              evidence: structuredClone(document.evidence),
            },
        events: [
          {
            name: recovering ? 'review_recovery_requested' : 'review_started',
            at: document.updated_at,
          },
        ],
        ...(recovering ? { resumed_from: previous!.id } : {}),
      })
      return route.fulfill({ status: 202, json: document })
    }
    if (path.endsWith('/evidence')) {
      expect(request.headers()['if-match']).toBe(document._etag)
      document.evidence.push(request.postDataJSON())
      document.status = 'draft'
      document._etag = String(Number(document._etag) + 1)
      return route.fulfill({ json: document })
    }
    if (document.status === 'running') {
      if (state.pollFailure) {
        const failure = state.pollFailure
        state.pollFailure = null
        return failure === 'network'
          ? route.abort('failed')
          : route.fulfill({ status: 429, json: { error: 'reviews_busy' } })
      }
      if (state.runningReads > 0) {
        state.runningReads--
        return route.fulfill({ json: document })
      }
      document.status = state.executions === 1 ? 'waiting_input' : 'completed'
      const run = document.runs.at(-1)!
      run.elapsed_ms = 1234
      run.result = {
        summary: 'Application evidence reviewed.',
        findings: [
          {
            criterion_id: 'CRIT-1',
            assessment: state.executions === 1 ? 'gap' : 'supported',
            explanation:
              state.executions === 1
                ? 'Budget is missing.'
                : 'Budget supplied.',
            citations:
              state.executions === 1
                ? []
                : [{ source_id: 'SRC-2', quote: 'Budget: $100.' }],
          },
          {
            criterion_id: 'CRIT-2',
            assessment: 'supported',
            explanation: 'A delivery timeline is stated.',
            citations: [
              {
                source_id: 'SRC-1',
                quote: 'Twelve weekly workshops beginning October 1.',
              },
            ],
          },
        ],
        questions:
          state.executions === 1 ? ['What is the project budget?'] : [],
      }
      run.events.push(
        { name: 'citations_checked', at: document.updated_at },
        { name: document.status, at: document.updated_at },
      )
      document._etag = String(Number(document._etag) + 1)
    }
    return route.fulfill({ json: document })
  })
  await page.goto('/#chat')
  await expect(page.locator('.agent-picker')).toContainText(
    'Checklist and case helper',
  )
  const navigation = workspaceNav(page)
  await expect(navigation.getByRole('button').first()).toHaveText('Chat')
  await expect(
    navigation.getByRole('button', { name: 'Chat', exact: true }),
  ).toHaveAttribute('aria-current', 'page')
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toBeVisible()
  await expect(
    navigation.getByRole('button', { name: 'Document reviews' }),
  ).toHaveCount(0)
  await expect(page.locator('.chat-review-link')).toHaveCount(0)
  await page.goto('/#reviews')
  await page.reload()
  await expect(
    navigation.getByRole('button', { name: 'Document reviews', exact: true }),
  ).toHaveAttribute('aria-current', 'page')
  await expect(
    page.getByRole('heading', { name: 'Document reviews', exact: true }),
  ).toBeVisible()
  return state
}

export async function create(page: Page) {
  await page.getByRole('button', { name: 'New review', exact: true }).click()
  await page.getByRole('button', { name: 'Use sample text' }).click()
  await page.getByRole('button', { name: 'Create shared review' }).click()
  await expect(
    page.getByRole('button', { name: 'Run review', exact: true }),
  ).toBeVisible()
}

export const sampleTitle = 'Community workshop application'

export async function expectReviewOpen(page: Page) {
  await expect(
    page.getByRole('heading', { name: sampleTitle, exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Run review', exact: true }),
  ).toBeVisible()
}

export async function interrupt(page: Page) {
  const state = await openReviews(page)
  await create(page)
  state.runningReads = 100
  await page.getByRole('button', { name: 'Run review', exact: true }).click()
  await expect(page.getByText('Running', { exact: true })).toBeVisible()
  state.document!.status = 'interrupted'
  state.document!.runs[0].error = 'execution_interrupted'
  state.document!.runs[0].events.push({
    name: 'interrupted',
    at: state.document!.updated_at,
  })
  state.document!._etag = '3'
  await page.reload()
  await expect(
    page.getByRole('button', { name: 'Recover review' }),
  ).toBeVisible()
  return state
}
