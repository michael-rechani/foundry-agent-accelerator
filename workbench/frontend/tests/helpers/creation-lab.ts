import { expect, type Page } from '@playwright/test'
import type {
  AgentTemplate,
  CreatePayload,
  CreatedAgent,
} from '../../src/agent-creation-client'
import type { Turn } from '../../src/conversation-types'
import { guidedReview } from '../fixtures'
import { catalog } from './catalog'
import { creationCapability, labConfig, modeFor } from './lab-config'
import { mockApi } from './mock-api'
import { openMadeInLab, waitForLab, workspaceNav } from './navigation'

export const operatorKey = 'fictional-test-key-not-a-real-secret-1234567890'
export const sample =
  'NOTICE-1: The fictional help desk opens at 09:00. NOTICE-2: A proposal says 08:00; no start date is supplied.'
const profiles: Record<string, AgentTemplate['model_profile']> = {
  reasoning: {
    id: 'reasoning',
    label: 'Reasoning',
    reason:
      'Compares sources step by step and keeps gaps and conflicts visible.',
  },
  extraction: {
    id: 'extraction',
    label: 'Fast extraction',
    reason: 'Copies stated values into a fixed structure.',
  },
  tool_calling: {
    id: 'tool_calling',
    label: 'Tool calling',
    reason: 'Calls lookup tools in the right order.',
  },
}
const templateProfiles: Record<string, string> = {
  'document-analyst': 'reasoning',
  'criteria-checker': 'reasoning',
  'document-intake': 'extraction',
  'casework-assistant': 'reasoning',
  'workflow-coordinator': 'tool_calling',
  'medical-bill-reviewer': 'reasoning',
  'insurance-preapproval-helper': 'reasoning',
  'benefits-renewal-helper': 'reasoning',
  'supplier-invoice-reviewer': 'reasoning',
}
const lookups: Record<string, string[]> = {
  'workflow-coordinator': ['lookup_demo_request', 'lookup_demo_service'],
  'medical-bill-reviewer': ['lookup_plan_benefits', 'lookup_usual_price'],
  'insurance-preapproval-helper': [
    'lookup_preapproval_rules',
    'lookup_facility',
  ],
  'benefits-renewal-helper': [
    'lookup_renewal_rules',
    'lookup_documents_on_file',
  ],
  'supplier-invoice-reviewer': [
    'lookup_purchase_order',
    'lookup_delivery_record',
  ],
}
export const categories = ['General', 'Healthcare and public sector']
export const templates: AgentTemplate[] = [
  [
    'document-analyst',
    'Document explainer',
    'Explain policy or product documents and identify questions for staff.',
  ],
  [
    'criteria-checker',
    'Checklist gap finder',
    'Compare a supplied checklist with labeled documents, without approving a submission.',
  ],
  [
    'document-intake',
    'Form field extractor',
    'Extract stated fields from sample administrative forms or invoices.',
  ],
  [
    'casework-assistant',
    'Case summary writer',
    'Summarize sample case notes and draft follow-up questions.',
  ],
  [
    'workflow-coordinator',
    'Service request planner',
    'Plan a sample service request using sample read-only lookups.',
  ],
  [
    'medical-bill-reviewer',
    'Medical bill reviewer',
    'Check a sample hospital bill against the insurer statement.',
  ],
  [
    'insurance-preapproval-helper',
    'Insurance pre-approval helper',
    'Check a sample pre-approval request has every required document.',
  ],
  [
    'benefits-renewal-helper',
    'Benefits renewal helper',
    'Sort sample renewal paperwork and flag what is missing.',
  ],
  [
    'supplier-invoice-reviewer',
    'Supplier invoice reviewer',
    'Compare what was ordered, delivered and billed.',
  ],
].map(([id, label, description], index) => ({
  id,
  category: categories[index < 5 ? 0 : 1],
  label,
  description,
  input: 'Supply labeled fictional text and a clear task.',
  output: 'A referenced response, missing information and follow-up questions.',
  limits:
    'No business, clinical, payment or eligibility decisions. No live writes. Human review required.',
  delegation: lookups[id]
    ? 'Uses two simulated read-only lookups, not specialist agents.'
    : 'Works directly on supplied text; no tools or other agents.',
  instructions: `Act as a ${label}. Use fictional supplied material, cite sources and ask for missing information.`,
  example_request: `Create a ${label} for a fictional demonstration.`,
  sample_input: sample,
  tools: (lookups[id] ?? []).map((name) => ({
    name,
    description: 'Read-only local fixture; no external system is contacted.',
    simulated: true,
  })),
  model_profile: profiles[templateProfiles[id]],
}))

export function recordFor(
  status: CreatedAgent['status'] = 'ready',
  payload: CreatePayload = {
    idempotency_key: '12345678-1234-4234-9234-123456789abc',
    template_id: templates[0].id,
    name: 'Policy notice helper',
    instructions: templates[0].instructions,
    confirm_cost: true,
  },
): CreatedAgent {
  const template = templates.find((item) => item.id === payload.template_id)!
  const id = 'created-' + payload.idempotency_key
  const runtime = 'lab-demo-' + payload.idempotency_key.replaceAll('-', '')
  return {
    id,
    name: status === 'deleted' ? 'Deleted agent' : payload.name,
    template_id: template.id,
    template_label: template.label,
    instructions: status === 'deleted' ? '' : payload.instructions,
    runtime_name: runtime,
    version: status === 'creating' ? null : '1',
    model: 'demo-reasoning-model',
    model_profile: template.model_profile,
    status,
    stage: status === 'creating' ? 'queued' : status,
    operation: 'create',
    created_at: '2027-04-12T10:00:00Z',
    updated_at: '2027-04-12T10:00:01Z',
    _etag: '"v1"',
    error: null,
    events: [
      {
        name: status === 'creating' ? 'queued' : status,
        at: '2027-04-12T10:00:01Z',
      },
    ],
    agent:
      status === 'ready'
        ? {
            id,
            agent: runtime,
            label: payload.name,
            category: 'Made in this Lab',
            description: template.description,
            tools: Object.fromEntries(
              template.tools.map((tool) => [tool.name, runtime]),
            ),
            prompts: [{ label: 'Try the sample', text: template.sample_input }],
            guidance: {
              input: template.input,
              output: template.output,
              limits: template.limits,
              delegation: template.delegation,
              configuration:
                'Saved task setup; the operator controls the model and fixed runtime tools.',
            },
          }
        : null,
  }
}

type ChatRequest = {
  agent_id: string
  input: string
  history: { role: string; content: string }[]
  thread: string
}
type SavedChat = {
  id: string
  title: string
  agent_id: string
  turns: Turn[]
  _etag: string
  updated_at: string
}

export async function openCreation(
  page: Page,
  options: {
    preview?: boolean
    disabled?: boolean
    saved?: CreatedAgent
    missingFromList?: boolean
    listFailure?: boolean
    templateFailure?: boolean
    hash?: string
    // Make the Agent designer reachable and have it answer with this text.
    designerAnswer?: string
  } = {},
) {
  const config = labConfig({
    mode: modeFor(options.preview),
    history_enabled: !options.preview,
    reviews_enabled: !options.preview,
    agent_creation: creationCapability(options),
    ...(options.designerAnswer
      ? {
          library_preview: {
            enabled: true,
            reason: null,
            agent: 'lab-library-preview',
          },
        }
      : {}),
  })
  const state = {
    record: options.saved || (null as CreatedAgent | null),
    drafts: [] as { goal: string; template_id?: string }[],
    posts: [] as CreatePayload[],
    keys: [] as string[],
    chat: [] as ChatRequest[],
    savedChat: null as SavedChat | null,
    polls: 0,
    lists: 0,
    deletes: 0,
    resumes: 0,
    hold: false,
    pollFailures: 0,
    loseResponse: false,
    persistLostResponse: false,
    rejectSetup: 0,
    invalidDraft: false,
    deletionFailure: false,
    missingFromList: !!options.missingFromList,
    listFailure: !!options.listFailure,
    templateFailure: !!options.templateFailure,
  }
  function update(
    status: CreatedAgent['status'],
    operation = state.record?.operation || 'create',
  ) {
    const current = state.record!
    const next = recordFor(status, {
      idempotency_key: current.id.slice(8),
      template_id: current.template_id,
      name: current.name,
      instructions: current.instructions,
      confirm_cost: true,
    })
    state.record = { ...next, operation, _etag: current._etag + '-next' }
    return state.record
  }
  await mockApi(page, async ({ route, request, path, method, respond }) => {
    if (path === '/api/config') return respond(config)
    if (path === '/api/agent-templates') {
      expect(request.headers()['x-workbench-request']).toBe('1')
      if (state.templateFailure)
        return respond({ error: 'agents_unavailable' }, 503)
      return respond(
        options.designerAnswer
          ? catalog
          : { templates, draft_mode: 'template' },
      )
    }
    if (path === '/api/agent-drafts') {
      const body = request.postDataJSON()
      state.drafts.push(body)
      expect(request.headers()['x-workbench-creation-key']).toBeUndefined()
      if (!body.template_id) return respond({ error: 'template_required' }, 400)
      const template = templates.find((item) => item.id === body.template_id)!
      return respond({
        template_id: template.id,
        name: template.label,
        goal: body.goal,
        instructions: template.instructions + '\nRequested job: ' + body.goal,
        sample_input: template.sample_input,
        source: state.invalidDraft ? 'model' : 'template',
      })
    }
    if (path === '/api/agents' && method === 'GET') {
      state.lists++
      if (state.listFailure)
        return respond({ error: 'agents_unavailable' }, 503)
      return respond({
        items:
          state.record &&
          state.record.status !== 'deleted' &&
          !state.missingFromList
            ? [state.record]
            : [],
        limit: 5,
      })
    }
    if (path === '/api/agents' && method === 'POST') {
      const body: CreatePayload = request.postDataJSON()
      state.posts.push(body)
      state.keys.push(request.headers()['x-workbench-creation-key'])
      expect(request.headers()['x-workbench-request']).toBe('1')
      expect(Object.keys(body).sort()).toEqual([
        'confirm_cost',
        'idempotency_key',
        'instructions',
        'name',
        'template_id',
      ])
      if (state.keys.at(-1) !== operatorKey)
        return respond({ error: 'operator_access_required' }, 403)
      if (state.rejectSetup)
        return respond(
          {
            error:
              state.rejectSetup === 413 ? 'request_too_large' : 'invalid_setup',
          },
          state.rejectSetup,
        )
      if (state.loseResponse) {
        state.loseResponse = false
        if (state.persistLostResponse)
          state.record = recordFor('creating', body)
        return route.abort('failed')
      }
      state.record = recordFor('creating', body)
      return respond(state.record, 202)
    }
    if (path.startsWith('/api/agents/')) {
      if (!state.record) return respond({ error: 'agent_not_found' }, 404)
      if (method === 'DELETE' || path.endsWith('/resume')) {
        expect(request.headers()['x-workbench-creation-key']).toBe(operatorKey)
        expect(request.headers()['if-match']).toBe(state.record._etag)
        expect(request.headers()['x-workbench-request']).toBe('1')
        if (method === 'DELETE') {
          state.deletes++
          return respond(update('deleting', 'delete'), 202)
        }
        state.resumes++
        return respond(update('creating', 'resume'), 202)
      }
      state.polls++
      if (state.pollFailures) {
        state.pollFailures--
        return respond({ error: 'agents_busy' }, 429)
      }
      if (state.record.status === 'creating' && !state.hold) update('ready')
      if (state.record.status === 'deleting') {
        if (state.deletionFailure) {
          state.deletionFailure = false
          update('interrupted', 'delete').error = 'deletion_unconfirmed'
        } else update('deleted', 'delete')
      }
      return respond(state.record)
    }
    if (path === '/api/reviews') {
      expect(request.headers()['x-workbench-creation-key']).toBeUndefined()
      state.chat.push(request.postDataJSON())
      if (
        options.designerAnswer &&
        state.chat.at(-1)!.agent_id === 'library-agent-designer'
      )
        return respond({
          request_id: 'illustrative-designer-1',
          status: 'completed',
          agent: 'lab-library-preview',
          text: options.designerAnswer,
          elapsed_ms: 900,
          receipts: [],
        })
      return respond({
        request_id: 'illustrative-response-1',
        status: 'completed',
        agent: state.record?.runtime_name || guidedReview.agent,
        text: 'ILLUSTRATIVE ANSWER: NOTICE-2 proposes earlier opening hours. The start date is missing.',
        elapsed_ms: 1100,
        receipts: [],
      })
    }
    if (path.startsWith('/api/conversations')) {
      if (method === 'POST') {
        const body = request.postDataJSON()
        state.savedChat = {
          ...body,
          id: 'aaaaaaaa-bbbb-4ccc-9ddd-eeeeeeeeeeee',
          _etag: '"chat-v1"',
          title: body.turns[0].question,
          updated_at: '2027-04-12T10:00:02Z',
        }
        return respond(state.savedChat)
      }
      if (path === '/api/conversations')
        return respond({
          items: state.savedChat ? [state.savedChat] : [],
          cursor: null,
        })
      return respond(state.savedChat)
    }
    if (path === '/api/review-runs') return respond({ items: [], cursor: null })
    return respond({ error: 'not_found' }, 404)
  })
  await page.goto('/' + (options.hash || '#create'))
  await waitForLab(page)
  return state
}

export async function navigate(page: Page, name: string) {
  if (name === 'Created agents') {
    await openMadeInLab(page)
    await expect(
      page.getByRole('heading', { level: 1, name: 'Made in this Lab' }),
    ).toBeVisible()
    return
  }
  await workspaceNav(page).getByRole('button', { name, exact: true }).click()
}

export async function prepare(page: Page, label = 'Document explainer') {
  await page
    .locator('.creation-template')
    .filter({ has: page.getByText(label, { exact: true }) })
    .click()
  await page.getByRole('button', { name: 'Prepare setup', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Review your agent setup' }),
  ).toBeVisible()
}

export async function authorize(page: Page, key = operatorKey) {
  await page.getByLabel('Operator key', { exact: true }).fill(key)
  await page.getByRole('checkbox').check()
}

export async function openSaved(page: Page, name = 'Policy notice helper') {
  await navigate(page, 'Created agents')
  await page
    .locator('.created-agent-list button')
    .filter({ has: page.getByText(name, { exact: true }) })
    .click()
  await expect(
    page.getByRole('region', { name: 'Created agent details' }),
  ).toBeVisible()
}
