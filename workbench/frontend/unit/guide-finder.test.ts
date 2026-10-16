import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { describe, it } from 'node:test'
import { findMatches, termsFor } from '../src/guide-finder.ts'
import { parseCatalog } from '../src/library-catalog.ts'

const catalog = parseCatalog(
  JSON.parse(
    await readFile(
      new URL('../tests/agent-templates.fixture.json', import.meta.url),
      'utf8',
    ),
  ),
)

const agent = (id: string, label: string, description: string) => ({
  id,
  label,
  category: 'Specialist',
  description,
  agent: id,
  tools: {},
  prompts: [{ label: 'Check against a checklist', text: '' }],
})
const agents = [
  agent('checklist', 'Checklist reviewer', 'Checks a document against a list.'),
  agent('notes', 'Case notes summarizer', 'Turns notes into a summary.'),
]

describe('guide finder', () => {
  it('drops filler words and stems the rest', () => {
    assert.deepEqual(termsFor('I want to be reviewing the invoices'), [
      'review',
      'invoic',
    ])
  })

  it('finds a ready agent by its name and its words', () => {
    const found = findMatches('summarize my case notes', agents, [])
    assert.equal(found.agents[0].id, 'notes')
  })

  it('finds templates from the library catalog', () => {
    const found = findMatches(
      'review a supplier invoice',
      [],
      catalog.templates,
    )
    assert.equal(found.templates[0].label, 'Supplier invoice reviewer')
  })

  it('does not repeat a template for an agent with the same name', () => {
    const named = [agent('invoice', 'Supplier invoice reviewer', 'Reviews.')]
    const found = findMatches('supplier invoice', named, catalog.templates)
    assert.equal(found.agents[0].id, 'invoice')
    assert.ok(found.templates.every((item) => item.label !== named[0].label))
  })

  it('returns nothing when no word matches or the text is only filler', () => {
    assert.deepEqual(findMatches('zzzz qqqq', agents, catalog.templates), {
      agents: [],
      templates: [],
    })
    assert.deepEqual(findMatches('what do I want to do', agents, []), {
      agents: [],
      templates: [],
    })
  })
})
