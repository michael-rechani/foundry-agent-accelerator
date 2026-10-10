import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  addOnGroupLabels,
  addOnRules,
  addOns,
  codingAgentRequest,
} from '../src/add-on-catalog.ts'

const everyText = () =>
  [
    ...addOnRules,
    ...addOns.flatMap((item) => [
      item.name,
      item.summary,
      item.example,
      item.pilot ?? '',
      ...item.cost,
      ...item.needs,
      item.safety,
      item.approval ?? '',
      item.service,
      item.billing,
      item.note ?? '',
    ]),
  ].join('\n')

describe('add-ons catalogue', () => {
  it('lists the eight planned add-ons once each', () => {
    assert.deepEqual(
      addOns.map((item) => item.id),
      [
        'knowledge-search',
        'conversation-memory',
        'document-extraction',
        'notifications',
        'code-interpreter',
        'web-search',
        'document-storage',
        'response-cache',
      ],
    )
  })

  it('reads each add-on from the generated catalogue with a known icon', () => {
    const icons = [
      'search',
      'memory',
      'documents',
      'notifications',
      'calculator',
      'web',
      'cache',
      'storage',
    ]
    assert.equal(new Set(addOns.map((item) => item.id)).size, addOns.length)
    for (const item of addOns) {
      assert.ok(icons.includes(item.icon), `${item.id} icon ${item.icon}`)
      assert.ok(item.name, `${item.id} name`)
    }
  })

  it('splits what an agent can do from what supports it', () => {
    const supports = addOns
      .filter((item) => item.group === 'support')
      .map((item) => item.id)
    assert.deepEqual(supports, [
      'conversation-memory',
      'document-storage',
      'response-cache',
    ])
    for (const item of addOns)
      assert.ok(
        item.group === 'abilities' || item.group === 'support',
        `${item.id} group`,
      )
    assert.equal(addOnGroupLabels.abilities, 'Lets an agent do more')
    assert.equal(addOnGroupLabels.support, 'Supports the agent')
  })

  it('warns that a cache keeps what people asked, like memory does', () => {
    const cache = addOns.find((item) => item.id === 'response-cache')
    assert.ok(cache)
    assert.match(cache.safety, /retention and deletion rules/)
    assert.match(cache.needs.join(' '), /never be saved/)
  })

  it('shows cost, needs and safety for every add-on before anything is on', () => {
    for (const item of addOns) {
      assert.ok(item.cost.length > 0, `${item.id} needs a cost`)
      assert.ok(item.needs.length > 0, `${item.id} needs a list of needs`)
      assert.ok(item.safety.length > 0, `${item.id} needs a safety note`)
      assert.ok(
        item.service && item.billing,
        `${item.id} needs technical detail`,
      )
    }
  })

  it('keeps web search behind an explicit approval', () => {
    for (const item of addOns)
      assert.equal(
        Boolean(item.approval),
        item.id === 'web-search',
        `${item.id} approval`,
      )
  })

  it('marks only knowledge search as a sample pilot already in the Lab', () => {
    for (const item of addOns)
      assert.equal(
        Boolean(item.pilot),
        item.id === 'knowledge-search',
        `${item.id} pilot`,
      )
    const pilot = addOns[0].pilot ?? ''
    assert.match(pilot, /Checklist and case helper/)
    assert.match(pilot, /ten approved sample passages/)
    assert.match(pilot, /own documents cannot be added yet/)
  })

  it('states the shared rules', () => {
    const rules = addOnRules.join(' ')
    for (const rule of [
      /Off by default/,
      /Private network/,
      /Managed identity/,
    ])
      assert.match(rules, rule)
    assert.match(rules, /explicit approval/)
  })

  it('builds a request that drafts a package and never deploys', () => {
    for (const item of addOns) {
      const request = codingAgentRequest(item)
      assert.ok(request.includes(`"${item.name}"`), `${item.id} name`)
      assert.ok(request.includes(`addons/${item.id}/addon.json`), item.id)
      for (const line of [...item.needs, ...item.cost])
        assert.ok(request.includes(`- ${line}`), `${item.id}: ${line}`)
      assert.match(request, /docs\/addon-package-format\.md/)
      assert.match(request, /python addons\/check_addons\.py/)
      assert.match(request, /Do not:/)
      assert.match(request, /Run terraform apply, deploy anything/)
      assert.match(request, /A person reviews and approves the saved plan/)
      assert.match(request, /public network access, a public IP, keys/)
    }
  })

  it('limits an add-on that needs approval to the approval request', () => {
    for (const item of addOns)
      assert.equal(
        codingAgentRequest(item).includes(
          'Draft the request for that approval only',
        ),
        Boolean(item.approval),
        `${item.id} approval`,
      )
  })

  it('uses the Lab wording: sample data, no invented brands', () => {
    const text = everyText()
    assert.doesNotMatch(text, /fictional|made-up|simulated|contoso/i)
    assert.match(addOnRules.join(' '), /Sample data/)
  })
})
