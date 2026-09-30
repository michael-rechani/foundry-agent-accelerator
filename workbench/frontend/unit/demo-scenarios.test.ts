import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { describe, it } from 'node:test'
import type { CreatedAgent } from '../src/agent-creation-client.ts'
import { agentForDemo, demoScenarios } from '../src/demo-scenarios.ts'
import { parseCatalog, previewAgents } from '../src/library-catalog.ts'
import type { Agent } from '../src/workspace-config.ts'

const catalog = parseCatalog(
  JSON.parse(
    await readFile(
      new URL('../tests/agent-templates.fixture.json', import.meta.url),
      'utf8',
    ),
  ),
)
const previews = previewAgents(catalog, 'lab-preview-agent')
const previewFor = (templateId: string) =>
  previews.find((item) => item.id === `library-${templateId}`)
const invoice = demoScenarios.find((item) => item.id === 'invoice')!
const application = demoScenarios.find((item) => item.id === 'application')!

function agent(id: string): Agent {
  return {
    id,
    label: id,
    category: 'Test',
    description: 'A test agent.',
    agent: id,
    tools: {},
    prompts: [],
  }
}

function created(
  templateId: string,
  status: CreatedAgent['status'],
  made: Agent | null,
): CreatedAgent {
  return {
    id: made?.id ?? 'created-none',
    name: 'Test copy',
    template_id: templateId,
    instructions: 'Test instructions.',
    runtime_name: 'lab-demo-test',
    version: '1',
    status,
    stage: status,
    created_at: '2027-04-12T10:00:00Z',
    updated_at: '2027-04-12T10:00:00Z',
    _etag: '"v1"',
    error: null,
    events: [],
    agent: made,
  }
}

describe('guided demo agent choice', () => {
  it('has a library preview for every demo template', () => {
    for (const scenario of demoScenarios)
      assert.ok(previewFor(scenario.templateId), scenario.templateId)
  })

  it('uses a configured agent before anything else', () => {
    const configured = agent('customer-review')
    const copy = agent('created-1')
    assert.equal(
      agentForDemo(
        application,
        [configured, copy],
        [created(application.templateId, 'ready', copy)],
        previewFor,
      ),
      configured,
    )
  })

  it('uses a ready agent made from the template before the preview', () => {
    const copy = agent('created-1')
    assert.equal(
      agentForDemo(
        invoice,
        [copy],
        [created(invoice.templateId, 'ready', copy)],
        previewFor,
      ),
      copy,
    )
  })

  it('falls back to the library preview when nothing else can run', () => {
    const chosen = agentForDemo(invoice, [], [], previewFor)
    assert.equal(chosen?.id, 'library-supplier-invoice-reviewer')
  })

  it('does not use an agent made from the template that is not ready', () => {
    for (const status of ['creating', 'failed', 'interrupted'] as const) {
      const copy = agent('created-1')
      const chosen = agentForDemo(
        invoice,
        [copy],
        [created(invoice.templateId, status, copy)],
        previewFor,
      )
      assert.equal(chosen?.id, 'library-supplier-invoice-reviewer', status)
    }
  })

  it('offers nothing when there is no preview for the template', () => {
    assert.equal(agentForDemo(invoice, [], []), undefined)
    assert.equal(
      agentForDemo(invoice, [], [], (templateId) =>
        templateId === invoice.templateId ? undefined : previewFor(templateId),
      ),
      undefined,
    )
  })
})
