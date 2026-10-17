import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  checkKey,
  clearDemoChecks,
  countChecks,
  demoChecksSnapshot,
  exportDemoChecks,
  parseChecks,
  summarizeChecks,
  toggleDemoCheck,
} from '../src/demo-checks.ts'
import { demoScenarios } from '../src/demo-scenarios.ts'

function fakeStore() {
  const data = new Map<string, string>()
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
  }
}

describe('demo test paths', () => {
  for (const scenario of demoScenarios) {
    it(`${scenario.id} has a sendable first step and checkable follow-ups`, () => {
      assert.ok(scenario.steps.length >= 2)
      assert.equal(scenario.steps[0].prompt, scenario.input)
      for (const step of scenario.steps) {
        assert.ok(step.title.trim())
        assert.ok(step.prompt.trim())
        assert.ok(step.expect.length >= 1)
        assert.ok(step.expect.every((item) => item.trim()))
      }
    })
  }

  it('keeps step titles unique within a scenario', () => {
    for (const scenario of demoScenarios) {
      const titles = scenario.steps.map((step) => step.title)
      assert.equal(new Set(titles).size, titles.length)
    }
  })
})

describe('demo check marks', () => {
  const scenario = demoScenarios[0]

  it('toggles, counts and clears marks per scenario', () => {
    const store = fakeStore()
    toggleDemoCheck(scenario.id, checkKey(0, 0), store)
    toggleDemoCheck(scenario.id, checkKey(1, 1), store)
    const marks = parseChecks(demoChecksSnapshot(scenario.id, store))
    const { passed, total } = countChecks(scenario, marks)
    assert.equal(passed, 2)
    assert.ok(total > passed)
    assert.equal(
      summarizeChecks(scenario, marks),
      `2 of ${total} checks passed`,
    )
    assert.equal(demoChecksSnapshot(demoScenarios[1].id, store), '')
    toggleDemoCheck(scenario.id, checkKey(0, 0), store)
    assert.equal(
      countChecks(scenario, parseChecks(demoChecksSnapshot(scenario.id, store)))
        .passed,
      1,
    )
    clearDemoChecks(scenario.id, store)
    assert.equal(demoChecksSnapshot(scenario.id, store), '')
  })

  it('ignores damaged stored marks', () => {
    assert.equal(parseChecks('not json').size, 0)
    assert.equal(parseChecks('{"a":1}').size, 0)
    assert.deepEqual([...parseChecks('["0.0",3]')], ['0.0'])
  })

  it('exports every check with its step and result', () => {
    const store = fakeStore()
    toggleDemoCheck(scenario.id, checkKey(0, 0), store)
    const exported = exportDemoChecks(scenario, store)
    assert.equal(exported.id, scenario.id)
    assert.equal(
      exported.checks.length,
      scenario.steps.reduce((sum, step) => sum + step.expect.length, 0),
    )
    assert.equal(exported.checks[0].passed, true)
    assert.equal(exported.checks[0].step, scenario.steps[0].title)
    assert.ok(exported.checks.slice(1).every((check) => !check.passed))
  })
})
