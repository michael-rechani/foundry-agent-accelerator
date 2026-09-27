import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { describe, it } from 'node:test'
import {
  filterTemplates,
  liveFacets,
  parseCatalog,
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
