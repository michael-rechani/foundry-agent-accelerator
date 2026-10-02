import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { describe, it } from 'node:test'
import {
  fieldGroups,
  filterTemplates,
  isPreviewId,
  liveFacets,
  openSector,
  parseCatalog,
  previewAgent,
  previewAgents,
  previewTemplateId,
  toggleFacet,
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

describe('sector and industry as one filter', () => {
  const counts = (
    facets: ReturnType<typeof liveFacets>,
    key: 'sectors' | 'industries',
  ) =>
    facets.find((group) => group.key === key)!.items.map((item) => item.count)

  it('lets one choice replace the other, and choosing it again clears it', () => {
    const sector = toggleFacet({}, 'sectors', 'public')
    assert.equal(sector.sectors, 'public')
    const industry = toggleFacet(sector, 'industries', 'finance')
    assert.equal(industry.sectors, undefined)
    assert.equal(industry.industries, 'finance')
    const again = toggleFacet(industry, 'sectors', 'private')
    assert.equal(again.industries, undefined)
    assert.equal(again.sectors, 'private')
    const cleared = toggleFacet(again, 'sectors', 'private')
    assert.equal(cleared.sectors, undefined)
    assert.equal(cleared.industries, undefined)
  })

  it('leaves the other filters alone and does not change its input', () => {
    const before = { sectors: 'public', tasks: 'review' }
    const after = toggleFacet(before, 'industries', 'finance')
    assert.deepEqual(before, { sectors: 'public', tasks: 'review' })
    assert.equal(after.tasks, 'review')
    assert.equal(toggleFacet(before, 'readiness', 'reviewed').sectors, 'public')
  })

  it('does not let one narrow the other but still applies the rest', () => {
    const catalog = parseCatalog(raw)
    const all = liveFacets(catalog, '', {})
    for (const selection of [
      { sectors: 'public' },
      { industries: 'finance' },
    ]) {
      const narrowed = liveFacets(catalog, '', selection)
      assert.deepEqual(counts(narrowed, 'sectors'), counts(all, 'sectors'))
      assert.deepEqual(
        counts(narrowed, 'industries'),
        counts(all, 'industries'),
      )
    }
    const review = filterTemplates(catalog, '', { tasks: 'review' }).length
    const reviewing = liveFacets(catalog, '', {
      sectors: 'public',
      tasks: 'review',
    })
    for (const key of ['sectors', 'industries'] as const)
      assert.equal(
        counts(reviewing, key).reduce((total, count) => total + count, 0),
        review,
      )
  })

  it('lists every industry once, under the sector its agents belong to', () => {
    const catalog = parseCatalog(raw)
    const groups = fieldGroups(
      catalog,
      catalog.facets.sectors,
      catalog.facets.industries,
    )
    assert.deepEqual(
      groups.map((group) => group.sector.id),
      catalog.facets.sectors.map((item) => item.id),
    )
    assert.deepEqual(
      groups.flatMap((group) => group.industries.map((item) => item.id)).sort(),
      catalog.facets.industries.map((item) => item.id).sort(),
    )
    for (const group of groups)
      for (const industry of group.industries)
        assert.ok(
          catalog.templates.some(
            (item) =>
              item.sector.id === group.sector.id &&
              item.industry.id === industry.id,
          ),
        )
  })

  it('opens the chosen sector, or the sector of the chosen industry', () => {
    const catalog = parseCatalog(raw)
    assert.equal(openSector(catalog, {}), undefined)
    assert.equal(openSector(catalog, { sectors: 'public' }), 'public')
    assert.equal(openSector(catalog, { industries: 'finance' }), 'private')
    assert.equal(
      openSector(catalog, { industries: 'procurement' }),
      'cross-sector',
    )
    assert.equal(openSector(catalog, { industries: 'nothing' }), undefined)
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

  it('recovers the template from a preview id and ignores other agents', () => {
    const [first] = previewAgents(parseCatalog(raw), 'lab-library-preview')
    assert.equal(previewTemplateId(first.id), parseCatalog(raw).templates[0].id)
    assert.equal(previewTemplateId('customer-review'), undefined)
    assert.equal(previewTemplateId('created-abc'), undefined)
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
