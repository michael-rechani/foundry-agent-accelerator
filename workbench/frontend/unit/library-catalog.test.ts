import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { describe, it } from 'node:test'
import {
  filterTemplates,
  isPreviewId,
  liveFacets,
  parseCatalog,
  previewAgent,
  previewAgents,
} from '../src/library-catalog.ts'

const raw = JSON.parse(
  await readFile(
    new URL('../tests/agent-templates.fixture.json', import.meta.url),
    'utf8',
  ),
)

describe('agent library catalog', () => {
  it('accepts the served catalog', () => {
    const catalog = parseCatalog(raw)
    assert.equal(catalog.templates.length, raw.templates.length)
  })

  it('rejects dishonest export claims and missing fields', () => {
    const exportable = structuredClone(raw)
    exportable.templates[0].export = {
      ...exportable.templates[0].export,
      exportable: true,
      availability: 'unavailable',
    }
    assert.throws(() => parseCatalog(exportable))
    const missing = structuredClone(raw)
    delete missing.templates[0].human_decision
    assert.throws(() => parseCatalog(missing))
    assert.throws(() => parseCatalog({ ...raw, schema_version: 2 }))
    assert.throws(() => parseCatalog({ ...raw, templates: [] }))
  })

  it('searches every term and combines facets', () => {
    const catalog = parseCatalog(raw)
    const invoices = filterTemplates(catalog, 'invoice', {})
    assert.ok(invoices.length > 0)
    assert.ok(
      invoices.every((item) =>
        JSON.stringify(item).toLowerCase().includes('invoice'),
      ),
    )
    const publicReview = filterTemplates(catalog, '', {
      sectors: 'public',
      tasks: 'review',
    })
    assert.ok(
      publicReview.every(
        (item) =>
          item.sector.id === 'public' &&
          item.tasks.some((task) => task.id === 'review'),
      ),
    )
    assert.deepEqual(filterTemplates(catalog, 'zzzz-no-match', {}), [])
  })

  it('keeps server facet order and counts other active filters', () => {
    const catalog = parseCatalog(raw)
    const unfiltered = liveFacets(catalog, '', {})
    for (const group of unfiltered)
      assert.deepEqual(
        group.items.map((item) => [item.id, item.count]),
        catalog.facets[group.key].map((item) => [item.id, item.count]),
      )
    const sectors = liveFacets(catalog, '', { sectors: 'public' })[0]
    assert.deepEqual(
      sectors.items.map((item) => item.count),
      catalog.facets.sectors.map((item) => item.count),
      'a facet does not narrow its own counts',
    )
    const readiness = liveFacets(catalog, '', { sectors: 'public' })[3]
    assert.equal(
      readiness.items.reduce((total, item) => total + item.count, 0),
      filterTemplates(catalog, '', { sectors: 'public' }).length,
    )
  })
})

describe('library previews', () => {
  it('maps each runnable template to a chat agent bound to the preview runtime', () => {
    const catalog = parseCatalog(raw)
    const agents = previewAgents(catalog, 'lab-library-preview')
    assert.equal(agents.length, catalog.templates.length)
    for (const [index, agent] of agents.entries()) {
      const template = catalog.templates[index]
      assert.equal(agent.id, `library-${template.id}`)
      assert.ok(isPreviewId(agent.id))
      assert.equal(agent.agent, 'lab-library-preview')
      assert.equal(agent.category, 'Library preview')
      assert.deepEqual(
        Object.keys(agent.tools),
        template.tools.map((tool) => tool.name),
      )
      assert.ok(
        Object.values(agent.tools).every(
          (target) => target === 'lab-library-preview',
        ),
      )
      assert.deepEqual(agent.prompts, [
        { label: 'Try the example', text: template.sample_input },
      ])
      assert.ok(agent.guidance)
      for (const text of Object.values(agent.guidance))
        assert.ok(text.trim() && [...text].length <= 1200)
      assert.match(agent.guidance.configuration, /Nothing is published/)
    }
  })

  it('offers no previews without a catalog, runtime or runnable template', () => {
    const catalog = parseCatalog(raw)
    assert.deepEqual(previewAgents(null, 'lab-library-preview'), [])
    assert.deepEqual(previewAgents(catalog, undefined), [])
    const connected = {
      ...catalog,
      templates: [
        {
          ...catalog.templates[0],
          tool_mode: {
            ...catalog.templates[0].tool_mode,
            id: 'connected-required',
          },
        },
      ],
    }
    assert.deepEqual(previewAgents(connected, 'lab-library-preview'), [])
    assert.equal(isPreviewId('customer-review'), false)
  })

  it('fills an empty delegation and clips long guidance', () => {
    const template = {
      ...parseCatalog(raw).templates[0],
      delegation: '',
      limits: 'x'.repeat(1500),
    }
    const agent = previewAgent(template, 'lab-library-preview')
    assert.equal(
      agent.guidance?.delegation,
      'Works directly on the text you supply.',
    )
    assert.equal([...(agent.guidance?.limits || '')].length, 1200)
  })
})
