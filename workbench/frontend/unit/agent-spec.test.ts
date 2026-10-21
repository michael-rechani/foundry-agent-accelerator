import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  parseAgentSpec,
  specDefinition,
  specFileName,
  validateSpec,
} from '../src/agent-spec.ts'
import { modelPlaceholder } from '../src/foundry-handoff.ts'

const spec = {
  name: 'Benefits Renewal Helper',
  summary: 'Helps a person renew benefits.',
  instructions: 'Ask for the renewal date, then list what is needed.',
  inputs: 'A renewal notice',
  outputs: 'A checklist',
  tools_needed: ['lookup_case'],
  human_decision: 'A caseworker decides eligibility.',
  closest_template: 'benefits-renewal-helper',
}
const reply = (body: string) =>
  `Here is the idea.\n\n\`\`\`agent-spec\n${body}\n\`\`\`\n`

describe('parseAgentSpec', () => {
  it('returns the spec and hides the block', () => {
    const parsed = parseAgentSpec(reply(JSON.stringify(spec)))
    assert.deepEqual(parsed.spec, spec)
    assert.equal(parsed.text, 'Here is the idea.')
  })

  it('uses the last valid block', () => {
    const later = { ...spec, name: 'Later' }
    const parsed = parseAgentSpec(
      reply(JSON.stringify(spec)) + reply(JSON.stringify(later)),
    )
    assert.equal(parsed.spec?.name, 'Later')
  })

  it('hides a block that is not JSON and returns no spec', () => {
    const parsed = parseAgentSpec(reply('{ not json'))
    assert.equal(parsed.spec, null)
    assert.equal(parsed.text, 'Here is the idea.')
  })

  it('returns no spec for a reply without a block', () => {
    const parsed = parseAgentSpec('What job should it do?')
    assert.equal(parsed.spec, null)
    assert.equal(parsed.text, 'What job should it do?')
  })
})

describe('validateSpec', () => {
  it('requires a name, summary, instructions and human decision', () => {
    for (const key of [
      'name',
      'summary',
      'instructions',
      'human_decision',
    ] as const) {
      assert.equal(validateSpec({ ...spec, [key]: '  ' }), null)
    }
    assert.equal(validateSpec(null), null)
    assert.equal(validateSpec([spec]), null)
  })

  it('cleans optional fields', () => {
    const cleaned = validateSpec({
      ...spec,
      tools_needed: ['a', 3, '', ' b '],
      closest_template: '',
    })
    assert.deepEqual(cleaned?.tools_needed, ['a', 'b'])
    assert.equal(cleaned?.closest_template, null)
  })

  it('caps the tool list', () => {
    const many = Array.from({ length: 30 }, (_, index) => `tool${index}`)
    assert.equal(validateSpec({ ...spec, tools_needed: many })?.tools_needed.length, 10)
  })
})

describe('specDefinition', () => {
  it('matches the shape of a library agent definition', () => {
    const file = specDefinition(spec)
    assert.equal(file.definition.kind, 'prompt')
    assert.equal(file.definition.model, modelPlaceholder)
    assert.equal(file.definition.instructions, spec.instructions)
    assert.deepEqual(file.definition.tools, [])
    assert.equal(file.metadata.source, 'Foundry Agent Lab Agent designer')
    assert.equal(file.metadata.tools_to_connect, 'lookup_case')
    assert.equal(file.metadata.closest_library_agent, 'benefits-renewal-helper')
  })

  it('names the file from the agent name', () => {
    assert.equal(specFileName(spec), 'benefits-renewal-helper.foundry-agent.json')
    assert.equal(specFileName({ name: '!!!' }), 'agent.foundry-agent.json')
  })
})
