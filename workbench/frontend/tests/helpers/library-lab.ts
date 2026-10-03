import { type Page, expect } from '@playwright/test'
import { guidedReview } from '../fixtures'
import { catalog, scorecardsWithout, support } from './catalog'
import {
  creationCapability,
  foundryPortal,
  labConfig,
  modeFor,
} from './lab-config'
import { mockApi } from './mock-api'
import { waitForLab } from './navigation'
import { type CreatedAgent } from '../../src/agent-creation-client'
import { type LibraryTemplate } from '../../src/library-catalog'

export const runtimeHash = 'a'.repeat(64)

export function readyRecord(template: LibraryTemplate): CreatedAgent {
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

export async function openLibrary(
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
    withoutCreation?: boolean
  } = {},
) {
  const config = labConfig({
    mode: modeFor(options.preview),
    reviews_enabled: false,
    foundry_portal: options.portal ? foundryPortal : null,
    ...(options.libraryPreview
      ? {
          library_preview: {
            enabled: true,
            reason: null,
            agent: 'lab-preview-agent',
          },
        }
      : {}),
    ...(options.withoutCreation
      ? {}
      : { agent_creation: creationCapability({ preview: options.preview }) }),
  })
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
  await mockApi(page, async ({ request, path, method, respond }) => {
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
      return respond(scorecardsWithout(options.withoutResultsFor))
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
  await waitForLab(page)
  return state
}

export async function openAgent(page: Page, label: string) {
  await page.locator('.library-card').filter({ hasText: label }).click()
  await expect(
    page.getByRole('heading', { level: 1, name: label, exact: true }),
  ).toBeVisible()
}
