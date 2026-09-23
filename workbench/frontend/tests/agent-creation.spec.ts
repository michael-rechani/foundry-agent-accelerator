import { expect, test, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import {
  parseCreatedAgent,
  type AgentTemplate,
  type CreatePayload,
  type CreatedAgent,
} from '../src/agent-creation-client'
import type { Config } from '../src/workspace-config'
import type { Turn } from '../src/conversation-types'
import { guidedReview, illustrativeScreenshot } from './fixtures'

const operatorKey = 'fictional-test-key-not-a-real-secret-1234567890'
const sample =
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
  'insurance-preapproval-helper': 'tool_calling',
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
const categories = ['General', 'Healthcare and public sector']
const templates: AgentTemplate[] = [
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
    'Form and invoice extractor',
    'Extract stated fields from fictional administrative forms or invoices.',
  ],
  [
    'casework-assistant',
    'Case notes summarizer',
    'Summarize fictional case notes and draft follow-up questions.',
  ],
  [
    'workflow-coordinator',
    'Service request planner',
    'Plan a fictional service request using simulated, read-only lookups.',
  ],
  [
    'medical-bill-reviewer',
    'Medical bill reviewer',
    'Check a fictional hospital bill against the insurer statement.',
  ],
  [
    'insurance-preapproval-helper',
    'Insurance pre-approval helper',
    'Check a fictional pre-approval request has every required document.',
  ],
  [
    'benefits-renewal-helper',
    'Benefits renewal helper',
    'Sort fictional renewal paperwork and flag what is missing.',
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

function recordFor(
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
            category: 'Created in this Lab',
            description: template.description,
            tools: Object.fromEntries(
              template.tools.map((tool) => [tool.name, runtime]),
            ),
            prompts: [
              { label: 'Try a fictional example', text: template.sample_input },
            ],
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
}
type SavedChat = {
  id: string
  title: string
  agent_id: string
  turns: Turn[]
  _etag: string
  updated_at: string
}

async function setup(
  page: Page,
  options: {
    preview?: boolean
    disabled?: boolean
    saved?: CreatedAgent
    missingFromList?: boolean
    listFailure?: boolean
    templateFailure?: boolean
    hash?: string
  } = {},
) {
  const config: Config = {
    title: 'AI Foundry Lab',
    mode: options.preview ? 'preview' : 'private',
    agents: [guidedReview],
    default_agent: guidedReview.id,
    max_characters: 60000,
    max_request_bytes: 65536,
    max_history_turns: 10,
    review_timeout_ms: 190000,
    history_timeout_ms: 45000,
    retention_days: 30,
    history_enabled: !options.preview,
    reviews_enabled: !options.preview,
    agent_creation: {
      enabled: !options.preview && !options.disabled,
      storage_enabled: !options.preview,
      management_enabled: !options.preview,
      reason: options.preview
        ? 'local_preview'
        : options.disabled
          ? 'not_enabled'
          : null,
      requires_operator_key: true,
      max_agents: 5,
      publication_timeout_seconds: 600,
      model: options.preview || options.disabled ? null : 'demo-model',
      models:
        options.preview || options.disabled
          ? null
          : {
              reasoning: 'demo-reasoning-model',
              extraction: 'demo-fast-model',
              tool_calling: 'demo-model',
            },
    },
  }
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
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const method = request.method()
    const respond = (json: unknown, status = 200) =>
      route.fulfill({ json, status })
    if (path === '/api/config') return respond(config)
    if (path === '/api/agent-templates') {
      expect(request.headers()['x-workbench-request']).toBe('1')
      if (state.templateFailure)
        return respond({ error: 'agents_unavailable' }, 503)
      return respond({ templates, draft_mode: 'template' })
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
  await page.goto('/' + (options.hash || ''))
  await expect(
    page.getByRole('navigation', { name: 'Workspace' }),
  ).toBeVisible()
  return state
}

async function navigate(page: Page, name: string) {
  await page
    .getByRole('navigation', { name: 'Workspace' })
    .getByRole('button', { name, exact: true })
    .click()
}

async function prepare(page: Page, label = 'Document explainer') {
  await page
    .locator('.creation-template')
    .filter({ has: page.getByText(label, { exact: true }) })
    .click()
  await page.getByRole('button', { name: 'Prepare setup', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Review your agent setup' }),
  ).toBeVisible()
}

async function authorize(page: Page, key = operatorKey) {
  await page.getByLabel('Operator key', { exact: true }).fill(key)
  await page.getByRole('checkbox').check()
}

async function openSaved(page: Page, name = 'Policy notice helper') {
  await navigate(page, 'Created agents')
  await page
    .locator('.created-agent-list button')
    .filter({ has: page.getByText(name, { exact: true }) })
    .click()
  await expect(
    page.getByRole('region', { name: 'Created agent details' }),
  ).toBeVisible()
}

test('creation is the entry point with nine honest jobs in two groups and usable navigation', async ({
  page,
}, testInfo) => {
  const state = await setup(page)
  await expect(
    page.getByRole('heading', { name: 'Create an agent', exact: true }),
  ).toBeVisible()
  await expect(page.locator('.creation-template strong')).toHaveText(
    templates.map((item) => item.label),
  )
  await expect(page.locator('.creation-template-group h2')).toHaveText(
    categories,
  )
  await expect(
    page
      .getByRole('region', { name: 'Healthcare and public sector' })
      .locator('.creation-template small'),
  ).toHaveText(Array(4).fill('Simulated read-only lookups'))
  await expect(
    page
      .getByRole('combobox', { name: 'Prepared template', exact: true })
      .locator('optgroup'),
  ).toHaveCount(2)
  await expect(page.locator('.creation-heading')).toContainText(
    'healthcare-administration',
  )
  await expect(page.locator('.creation-steps li')).toHaveText([
    'Describe the job',
    'Review name, instructions and tools',
    'Create in Foundry and try it',
  ])
  await expect(
    page.getByRole('button', { name: 'Prepare setup', exact: true }),
  ).toBeDisabled()
  for (const label of [
    'Create agent',
    'Created agents',
    'Chat',
    'Document reviews',
    'Shared history',
    'Agents',
    'Performance',
  ]) {
    await expect(
      page.getByRole('navigation').getByRole('button', {
        name: label === 'Agents' ? /^Agents\b/ : label,
        exact: label !== 'Agents',
      }),
    ).toBeVisible()
  }
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  expect(state.posts).toHaveLength(0)
  expect(state.chat).toHaveLength(0)
  await illustrativeScreenshot(page, testInfo, 'creation-start.png')
})

test('template selection preserves custom input and brings the next step into view', async ({
  page,
}) => {
  await setup(page)
  const goal = page.getByLabel('What should the agent help with?')
  await goal.fill(
    'Explain the differences between my fictional policy notices.',
  )
  await page.locator('.creation-template').first().click()
  await expect(goal).toHaveValue(
    'Explain the differences between my fictional policy notices.',
  )
  await expect(goal).toBeFocused()
  await expect(goal).toBeInViewport()
  await page.getByRole('button', { name: 'Prepare setup', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Review your agent setup' }),
  ).toBeInViewport()
})

test('ambiguous descriptions require a template and preparation creates no agent', async ({
  page,
}) => {
  const state = await setup(page)
  await page
    .getByLabel('What should the agent help with?')
    .fill('Help our fictional team with its work')
  await page.getByRole('button', { name: 'Prepare setup', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText(
    'Choose the closest prepared template',
  )
  await page
    .getByRole('combobox', { name: 'Prepared template', exact: true })
    .selectOption('casework-assistant')
  await page.getByRole('button', { name: 'Prepare setup', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Review your agent setup' }),
  ).toBeVisible()
  await expect(page.getByLabel('Agent name', { exact: true })).toHaveValue(
    'Case notes summarizer',
  )
  await expect(page.getByLabel('Task instructions')).toHaveValue(
    /Help our fictional team/,
  )
  await expect(
    page.getByRole('region', { name: 'Review agent setup' }),
  ).toContainText('No agent has been created yet')
  expect(state.drafts).toHaveLength(2)
  expect(state.posts).toHaveLength(0)
  expect(state.chat).toHaveLength(0)
})

test('publishes reviewed setup, uses its real ID in chat, saves and restores history without leaking keys', async ({
  page,
}, testInfo) => {
  const state = await setup(page)
  await prepare(page)
  await expect(page.locator('.creation-explanation')).toContainText(
    'demo-reasoning-model, chosen for Reasoning.',
  )
  await page
    .getByLabel('Agent name', { exact: true })
    .fill('Policy notice helper')
  await page
    .getByLabel('Task instructions')
    .fill(
      'Explain fictional policy notices. Cite labels and ask for the missing implementation date.',
    )
  await expect(
    page.getByRole('button', { name: 'Create in Foundry', exact: true }),
  ).toBeDisabled()
  await authorize(page)
  await page
    .getByRole('region', { name: 'Review agent setup' })
    .scrollIntoViewIfNeeded()
  await illustrativeScreenshot(page, testInfo, 'creation-setup.png')
  await page
    .getByRole('button', { name: 'Create in Foundry', exact: true })
    .click()
  await expect(page.locator('.creation-status')).toHaveText('Ready to try')
  await expect(page.getByLabel('Operator key', { exact: true })).toHaveValue('')
  expect(state.posts).toHaveLength(1)
  expect(state.posts[0].name).toBe('Policy notice helper')
  expect(state.posts[0].instructions).toContain('missing implementation date')
  await expect(page.locator('.creation-runtime')).toContainText(
    'demo-reasoning-model, chosen for Reasoning',
  )
  await page
    .getByRole('heading', { name: 'Policy notice helper', exact: true })
    .scrollIntoViewIfNeeded()
  await illustrativeScreenshot(page, testInfo, 'creation-ready.png')
  await page.getByRole('button', { name: 'Try in Chat', exact: true }).click()
  await expect(page.locator('.agent-picker')).toContainText(
    'Policy notice helper',
  )
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue('')
  expect(state.chat).toHaveLength(0)
  await page
    .getByRole('button', { name: 'Try a fictional example', exact: true })
    .click()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue(sample)
  expect(state.chat).toHaveLength(0)
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
  await expect(
    page.getByRole('button', { name: 'Save to shared history' }),
  ).toBeEnabled()
  expect(state.chat).toEqual([
    { agent_id: state.record!.id, input: sample, history: [] },
  ])
  await illustrativeScreenshot(page, testInfo, 'creation-chat.png')
  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export conversation' }).click()
  const download = await downloadEvent
  const exported = await readFile((await download.path())!, 'utf8')
  expect(exported).not.toContain(operatorKey)
  expect(exported).not.toContain(state.posts[0].instructions)
  expect(
    await page.evaluate(() =>
      JSON.stringify({ ...localStorage, ...sessionStorage }),
    ),
  ).not.toContain(operatorKey)
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect.poll(() => state.savedChat?.agent_id).toBe(state.record!.id)
  state.missingFromList = true
  await page.reload()
  await navigate(page, 'Shared history')
  await page
    .getByRole('button', { name: new RegExp('^' + sample.slice(0, 12)) })
    .click()
  await expect(page.locator('.agent-picker')).toContainText(
    'Policy notice helper',
  )
  await expect(page.getByText(/ILLUSTRATIVE ANSWER:/)).toBeVisible()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toBeEnabled()
  expect(state.posts).toHaveLength(1)
})

test('local preview prepares all nine templates but cannot publish or load saved agents', async ({
  page,
}, testInfo) => {
  const state = await setup(page, { preview: true })
  for (const template of templates) {
    await prepare(page, template.label)
    await expect(
      page.getByRole('button', { name: 'Create in Foundry', exact: true }),
    ).toBeDisabled()
    await expect(
      page.getByLabel('Operator key', { exact: true }),
    ).toBeDisabled()
    await expect(page.getByText('Local preview', { exact: true })).toBeVisible()
    await expect(page.locator('.creation-explanation')).toContainText(
      `Set by the Lab operator, chosen for ${template.model_profile.label}.`,
    )
    if (template.tools.length) {
      await expect(page.locator('.creation-tool-list li')).toHaveCount(2)
      await expect(page.locator('.creation-tool-list')).toContainText(
        'SIMULATED',
      )
      if (template.id === 'medical-bill-reviewer')
        await illustrativeScreenshot(
          page,
          testInfo,
          'creation-preview-tools.png',
        )
    } else
      await expect(
        page.getByText('No tools or external integrations.', { exact: true }),
      ).toBeVisible()
    await page.getByRole('button', { name: 'Change task or template' }).click()
  }
  await navigate(page, 'Created agents')
  await expect(page.locator('.creation-workspace')).toContainText(
    'Created-agent storage is not connected',
  )
  expect(state.lists).toBe(0)
  expect(state.posts).toHaveLength(0)
  expect(state.chat).toHaveLength(0)
})

test('incorrect operator key preserves editable setup and does not claim success', async ({
  page,
}) => {
  const state = await setup(page)
  await prepare(page)
  await authorize(page, 'incorrect-fictional-key-12345678901234567890')
  await page
    .getByRole('button', { name: 'Create in Foundry', exact: true })
    .click()
  await expect(page.getByRole('alert')).toContainText(
    'Enter a valid operator key',
  )
  await expect(page.getByLabel('Agent name', { exact: true })).toBeEnabled()
  await expect(page.getByLabel('Task instructions')).toBeEnabled()
  expect(state.record).toBeNull()
  await page.getByLabel('Operator key', { exact: true }).fill(operatorKey)
  await page
    .getByRole('button', { name: 'Create in Foundry', exact: true })
    .click()
  await expect(page.locator('.creation-status')).toHaveText('Ready to try')
  expect(state.posts).toHaveLength(2)
})

for (const rejection of [400, 413]) {
  test(`rejected setup (${rejection}) stays editable rather than locking an unaccepted operation`, async ({
    page,
  }) => {
    const state = await setup(page)
    state.rejectSetup = rejection
    await prepare(page)
    await authorize(page)
    await page
      .getByRole('button', { name: 'Create in Foundry', exact: true })
      .click()
    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page.getByLabel('Agent name', { exact: true })).toHaveValue(
      'Document explainer',
    )
    await expect(page.getByLabel('Task instructions')).toBeEnabled()
    await expect(
      page.getByRole('button', { name: 'Retry same creation request' }),
    ).toHaveCount(0)
    expect(state.record).toBeNull()
  })
}

test('uncertain response retains the same UUID and body for explicit retry only', async ({
  page,
}) => {
  await page.clock.install()
  const state = await setup(page)
  state.loseResponse = true
  await prepare(page)
  await authorize(page)
  await page
    .getByRole('button', { name: 'Create in Foundry', exact: true })
    .click()
  await expect(
    page.getByRole('button', { name: 'Retry same creation request' }),
  ).toBeVisible()
  await expect(page.getByLabel('Agent name', { exact: true })).toBeDisabled()
  await page.clock.fastForward(35000)
  expect(state.posts).toHaveLength(1)
  await page.getByRole('button', { name: 'Check creation status' }).click()
  await expect(page.getByRole('alert')).toContainText('No saved agent record')
  await page
    .getByRole('button', { name: 'Retry same creation request' })
    .click()
  await expect(page.locator('.creation-status')).toHaveText('Ready to try')
  expect(state.posts).toHaveLength(2)
  expect(state.posts[1]).toEqual(state.posts[0])
})

test('lost response with a saved operation recovers using GET, never another publication', async ({
  page,
}) => {
  const state = await setup(page)
  state.loseResponse = true
  state.persistLostResponse = true
  await prepare(page)
  await authorize(page)
  await page
    .getByRole('button', { name: 'Create in Foundry', exact: true })
    .click()
  await expect(
    page.getByRole('button', { name: 'Check creation status' }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Check creation status' }).click()
  await expect(page.locator('.creation-status')).toHaveText('Ready to try')
  expect(state.posts).toHaveLength(1)
})

test('poll failure pauses checks until explicit refresh without posting again', async ({
  page,
}) => {
  await page.clock.install()
  const state = await setup(page)
  state.pollFailures = 1
  await prepare(page)
  await authorize(page)
  await page
    .getByRole('button', { name: 'Create in Foundry', exact: true })
    .click()
  await expect(page.getByRole('status')).toContainText(
    'automatic checks paused',
  )
  const reads = state.polls
  await page.clock.fastForward(45000)
  expect(state.polls).toBe(reads)
  expect(state.posts).toHaveLength(1)
  await page.getByRole('button', { name: 'Refresh status' }).click()
  await expect(page.locator('.creation-status')).toHaveText('Ready to try')
  expect(state.posts).toHaveLength(1)
})

test('ready agents persist across reload and new-chat confirmation preserves unsaved messages', async ({
  page,
}) => {
  const state = await setup(page, { saved: recordFor() })
  await navigate(page, 'Chat')
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Keep this fictional unsent message')
  await openSaved(page)
  page.once('dialog', (dialog) => dialog.dismiss())
  await page.getByRole('button', { name: 'Try in Chat', exact: true }).click()
  await expect(
    page.getByRole('region', { name: 'Created agent details' }),
  ).toBeVisible()
  await navigate(page, 'Chat')
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue('Keep this fictional unsent message')
  await navigate(page, 'Created agents')
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Try in Chat', exact: true }).click()
  await expect(page.locator('.agent-picker')).toContainText(
    'Policy notice helper',
  )
  await page.reload()
  await openSaved(page)
  await expect(page.locator('.creation-status')).toHaveText('Ready to try')
  expect(state.posts).toHaveLength(0)
})

test('leaving creation removes the password without losing the prepared task', async ({
  page,
}) => {
  await setup(page)
  await prepare(page)
  await page.getByLabel('Operator key', { exact: true }).fill(operatorKey)
  await navigate(page, 'Chat')
  await expect(page.locator('input[type="password"]')).toHaveCount(0)
  await navigate(page, 'Create agent')
  await expect(page.getByLabel('Agent name', { exact: true })).toHaveValue(
    'Document explainer',
  )
  await expect(page.getByLabel('Operator key', { exact: true })).toHaveValue('')
  expect(
    await page.evaluate(() =>
      JSON.stringify({ ...localStorage, ...sessionStorage }),
    ),
  ).not.toContain(operatorKey)
})

test('deletion stays available with creation disabled and requires confirmation and current ETag', async ({
  page,
}) => {
  const state = await setup(page, { disabled: true, saved: recordFor() })
  await openSaved(page)
  await page.getByLabel('Operator key', { exact: true }).fill(operatorKey)
  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('for everyone')
    expect(dialog.message()).toContain('Export needed chats first')
    await dialog.dismiss()
  })
  await page.getByRole('button', { name: 'Delete created agent' }).click()
  expect(state.deletes).toBe(0)
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Delete created agent' }).click()
  await expect(page.locator('.creation-status')).toHaveText('Deleted')
  await expect(page.locator('.creation-detail')).toContainText(
    'Deletion was confirmed',
  )
  await expect(
    page.getByRole('button', { name: 'Try in Chat', exact: true }),
  ).toHaveCount(0)
  expect(state.record!.instructions).toBe('')
  expect(state.deletes).toBe(1)
  expect(state.posts).toHaveLength(0)
  await page.getByRole('button', { name: 'Back to created agents' }).click()
  await expect(page.locator('.created-agent-list')).toHaveCount(0)
})

test('interrupted setup resumes an existing operation, but interrupted deletion cannot resume setup', async ({
  page,
}) => {
  const interrupted = {
    ...recordFor('interrupted'),
    error: 'publication_unconfirmed',
  }
  const state = await setup(page, { saved: interrupted })
  await openSaved(page)
  await page.getByLabel('Operator key', { exact: true }).fill(operatorKey)
  await page.getByRole('button', { name: 'Resume setup' }).click()
  await expect(page.locator('.creation-status')).toHaveText('Ready to try')
  expect(state.resumes).toBe(1)
  expect(state.posts).toHaveLength(0)
  state.deletionFailure = true
  await page.getByLabel('Operator key', { exact: true }).fill(operatorKey)
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Delete created agent' }).click()
  await expect(page.locator('.creation-status')).toHaveText('Check outcome')
  await expect(page.locator('.creation-detail')).toContainText(
    'Deletion is not confirmed',
  )
  await expect(page.getByRole('button', { name: 'Resume setup' })).toHaveCount(
    0,
  )
  await page.getByLabel('Operator key', { exact: true }).fill(operatorKey)
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Delete created agent' }).click()
  await expect(page.locator('.creation-status')).toHaveText('Deleted')
  expect(state.deletes).toBe(2)
})

test('template and collection errors stay visible and can be refreshed', async ({
  page,
}) => {
  const state = await setup(page, { templateFailure: true, listFailure: true })
  await expect(
    page.getByRole('button', { name: 'Retry templates' }),
  ).toBeVisible()
  state.templateFailure = false
  await page.getByRole('button', { name: 'Retry templates' }).click()
  await expect(page.locator('.creation-template')).toHaveCount(9)
  await navigate(page, 'Created agents')
  await expect(page.getByRole('alert')).toContainText('storage is unavailable')
  state.listFailure = false
  await page.getByRole('button', { name: 'Refresh agents' }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  expect(state.posts).toHaveLength(0)
})

test('malformed prepared setup cannot become a publishable draft', async ({
  page,
}) => {
  const state = await setup(page)
  state.invalidDraft = true
  await page.locator('.creation-template').first().click()
  await page.getByRole('button', { name: 'Prepare setup', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText(
    'prepared setup response is invalid',
  )
  await expect(
    page.getByRole('button', { name: 'Create in Foundry', exact: true }),
  ).toHaveCount(0)
  expect(state.posts).toHaveLength(0)
})

test('saved-review links still open document reviews instead of the new default entry', async ({
  page,
}) => {
  const state = await setup(page, {
    hash: '#review-12345678-1234-1234-1234-123456789abc',
  })
  await expect(
    page.getByRole('heading', { name: 'Document reviews', exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'Create an agent', exact: true }),
  ).toBeHidden()
  expect(state.posts).toHaveLength(0)
  expect(state.chat).toHaveLength(0)
})

test('created-record validation rejects mismatched identities and accepts cleared deletion tombstones', () => {
  const record = recordFor()
  expect(parseCreatedAgent(record).id).toBe(record.id)
  expect(parseCreatedAgent(recordFor('deleted')).instructions).toBe('')
  expect(() =>
    parseCreatedAgent({
      ...record,
      agent: { ...record.agent!, id: guidedReview.id },
    }),
  ).toThrow()
  expect(() =>
    parseCreatedAgent({
      ...record,
      agent: { ...record.agent!, agent: guidedReview.agent },
    }),
  ).toThrow()
  expect(() => parseCreatedAgent({ ...record, status: 'creating' })).toThrow()
  expect(() =>
    parseCreatedAgent({ ...record, model_profile: { id: 'reasoning' } }),
  ).toThrow()
  expect(
    parseCreatedAgent({ ...record, model_profile: undefined }).model_profile,
  ).toBeUndefined()
  expect(() => parseCreatedAgent({ ...record, instructions: '' })).toThrow()
})
