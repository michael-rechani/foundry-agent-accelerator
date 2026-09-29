import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { describe, it } from 'node:test'
import {
  agentDefinition,
  definitionFileName,
  evaluationFileName,
  evaluationLines,
  modelPlaceholder,
} from '../src/foundry-handoff.ts'
import { parseCatalog } from '../src/library-catalog.ts'
import { parseScorecards } from '../src/scorecards.ts'

const catalog = parseCatalog(
  JSON.parse(
    await readFile(
      new URL('../tests/agent-templates.fixture.json', import.meta.url),
      'utf8',
    ),
  ),
)
const scorecards = parseScorecards(
  JSON.parse(
    await readFile(
      new URL('../../agent_scorecards.json', import.meta.url),
      'utf8',
    ),
  ),
)

describe('Foundry handoff files', () => {
  it('builds a prompt agent definition with a model slot and no tools', () => {
    const template = catalog.templates.find((item) => item.tools.length)!
    const body = agentDefinition(template)
    assert.equal(body.definition.kind, 'prompt')
    assert.equal(body.definition.model, modelPlaceholder)
    assert.equal(body.definition.instructions, template.instructions)
    assert.deepEqual(body.definition.tools, [])
    assert.equal(body.metadata.library_agent, template.id)
    assert.equal(
      body.metadata.tools_to_connect,
      template.tools.map((tool) => tool.name).join(', '),
    )
    assert.ok(Object.values(body.metadata).every((v) => v.length <= 512))
    assert.equal(
      definitionFileName(template.id),
      `${template.id}.foundry-agent.json`,
    )
  })

  it('leaves out the tool list for agents that use none', () => {
    const template = catalog.templates.find((item) => !item.tools.length)!
    assert.equal(
      'tools_to_connect' in agentDefinition(template).metadata,
      false,
    )
  })

  it('keeps long metadata inside the limit', () => {
    const template = {
      ...catalog.templates[0],
      human_decision: 'x'.repeat(900),
    }
    const value = agentDefinition(template).metadata.who_decides
    assert.equal([...value].length, 512)
    assert.ok(value.endsWith('…'))
  })

  it('writes one evaluation row per case, with the request in query', () => {
    const card = scorecards.scorecards[0]
    const lines = evaluationLines(card.cases).trimEnd().split('\n')
    assert.equal(lines.length, card.cases.length)
    const first = JSON.parse(lines[0])
    assert.deepEqual(Object.keys(first), [
      'query',
      'case_id',
      'category',
      'expected_behavior',
    ])
    assert.equal(first.query, card.cases[0].input)
    assert.equal(first.expected_behavior, card.cases[0].goal)
    assert.equal(evaluationFileName('a-b'), 'a-b.foundry-test-cases.jsonl')
  })

  it('keeps line breaks in requests inside their own row', () => {
    const lines = evaluationLines([
      { id: 'c', category: 'grounded', goal: 'g', input: 'one\ntwo' },
    ])
    assert.equal(lines.split('\n').length, 2)
    assert.equal(JSON.parse(lines).query, 'one\ntwo')
  })
})
