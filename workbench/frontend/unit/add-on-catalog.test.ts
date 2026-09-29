import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { addOnRules, addOns } from '../src/add-on-catalog.ts'

const everyText = () =>
  [
    ...addOnRules,
    ...addOns.flatMap((item) => [
      item.name,
      item.summary,
      item.example,
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
  it('lists the six planned add-ons once each', () => {
    assert.deepEqual(
      addOns.map((item) => item.id),
      [
        'knowledge-search',
        'conversation-memory',
        'document-extraction',
        'notifications',
        'code-interpreter',
        'web-search',
      ],
    )
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

  it('uses the Lab wording: sample data, no invented brands', () => {
    const text = everyText()
    assert.doesNotMatch(text, /fictional|made-up|simulated|contoso/i)
    assert.match(addOnRules.join(' '), /Sample data/)
  })
})
