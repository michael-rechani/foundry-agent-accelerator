import type { DemoScenario } from './demo-scenarios'

// Pass marks for a demo test path. They stay in this browser tab's session
// storage: nothing is sent to the server or shared.
type Store = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

const prefix = 'ai-foundry-lab-demo-checks:'
const listeners = new Set<() => void>()
const memory = new Map<string, string>()
const memoryStore: Store = {
  getItem: (key) => memory.get(key) ?? null,
  setItem: (key, value) => void memory.set(key, value),
  removeItem: (key) => void memory.delete(key),
}

function browserStore(): Store {
  try {
    if (typeof sessionStorage !== 'undefined') return sessionStorage
  } catch {
    // Storage can be blocked; marks then last until the page is reloaded.
  }
  return memoryStore
}

export const checkKey = (step: number, item: number) => `${step}.${item}`

export function demoChecksSnapshot(
  scenarioId: string,
  store: Store = browserStore(),
) {
  return store.getItem(prefix + scenarioId) ?? ''
}

export function subscribeDemoChecks(listener: () => void) {
  listeners.add(listener)
  return () => void listeners.delete(listener)
}

export function parseChecks(raw: string): Set<string> {
  try {
    const value: unknown = raw ? JSON.parse(raw) : []
    return new Set(
      Array.isArray(value)
        ? value.filter((item): item is string => typeof item === 'string')
        : [],
    )
  } catch {
    return new Set()
  }
}

function write(scenarioId: string, marks: Set<string>, store: Store) {
  if (marks.size) {
    store.setItem(prefix + scenarioId, JSON.stringify([...marks].sort()))
  } else {
    store.removeItem(prefix + scenarioId)
  }
  listeners.forEach((listener) => listener())
}

export function toggleDemoCheck(
  scenarioId: string,
  key: string,
  store: Store = browserStore(),
) {
  const marks = parseChecks(demoChecksSnapshot(scenarioId, store))
  if (!marks.delete(key)) marks.add(key)
  write(scenarioId, marks, store)
}

export function clearDemoChecks(
  scenarioId: string,
  store: Store = browserStore(),
) {
  write(scenarioId, new Set(), store)
}

export function countChecks(scenario: DemoScenario, marks: Set<string>) {
  let passed = 0
  let total = 0
  scenario.steps.forEach((step, stepIndex) =>
    step.expect.forEach((_, itemIndex) => {
      total += 1
      if (marks.has(checkKey(stepIndex, itemIndex))) passed += 1
    }),
  )
  return { passed, total }
}

export function summarizeChecks(scenario: DemoScenario, marks: Set<string>) {
  const { passed, total } = countChecks(scenario, marks)
  return `${passed} of ${total} checks passed`
}

// The shape added to an exported conversation.
export function exportDemoChecks(
  scenario: DemoScenario,
  store: Store = browserStore(),
) {
  const marks = parseChecks(demoChecksSnapshot(scenario.id, store))
  return {
    id: scenario.id,
    title: scenario.title,
    summary: summarizeChecks(scenario, marks),
    checks: scenario.steps.flatMap((step, stepIndex) =>
      step.expect.map((expectation, itemIndex) => ({
        step: step.title,
        expectation,
        passed: marks.has(checkKey(stepIndex, itemIndex)),
      })),
    ),
  }
}
