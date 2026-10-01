import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { describe, it } from 'node:test'
import { agentIcons, fallbackAgentIcon } from '../src/agent-icons.ts'
import { parseCatalog } from '../src/library-catalog.ts'

const catalog = parseCatalog(
  JSON.parse(
    await readFile(
      new URL('../tests/agent-templates.fixture.json', import.meta.url),
      'utf8',
    ),
  ),
)
const ids = catalog.templates.map((item) => item.id)

describe('agent icons', () => {
  it('gives every library agent an icon and no icon to an agent that is not there', () => {
    assert.deepEqual(Object.keys(agentIcons).sort(), [...ids].sort())
  })

  it('gives each agent its own icon so cards can be told apart at a glance', () => {
    const used = new Set(ids.map((id) => agentIcons[id]))
    assert.equal(used.size, ids.length)
    assert.ok(!used.has(fallbackAgentIcon))
  })
})
