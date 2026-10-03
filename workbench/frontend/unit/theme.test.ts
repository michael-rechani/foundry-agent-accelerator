import assert from 'node:assert/strict'
import { afterEach, describe, it } from 'node:test'
import {
  defaultTheme,
  loadTheme,
  parseTheme,
  saveTheme,
  themeStorageKey,
} from '../src/theme.ts'

const storage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')

function useStorage(value: unknown) {
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value,
  })
}

afterEach(() => {
  if (storage) Object.defineProperty(globalThis, 'localStorage', storage)
  else Reflect.deleteProperty(globalThis, 'localStorage')
})

describe('parseTheme', () => {
  it('accepts a saved mode, accent and look', () => {
    assert.deepEqual(
      parseTheme('{"mode":"dark","accent":"lagoon","look":"aurora"}'),
      { mode: 'dark', accent: 'lagoon', look: 'aurora' },
    )
    assert.equal(parseTheme('{"look":"console"}').look, 'console')
  })

  it('replaces each unknown field independently', () => {
    assert.deepEqual(
      parseTheme('{"mode":"sepia","accent":"orchid","look":"console"}'),
      { mode: defaultTheme.mode, accent: 'orchid', look: 'console' },
    )
    assert.deepEqual(
      parseTheme('{"mode":"light","accent":7,"look":"aurora"}'),
      { mode: 'light', accent: defaultTheme.accent, look: 'aurora' },
    )
    assert.deepEqual(
      parseTheme('{"mode":"light","accent":"orchid","look":"neon"}'),
      { mode: 'light', accent: 'orchid', look: defaultTheme.look },
    )
    assert.equal(parseTheme('{"look":["aurora"]}').look, defaultTheme.look)
  })

  it('opens a value saved before looks existed in Classic', () => {
    assert.deepEqual(parseTheme('{"mode":"dark","accent":"lagoon"}'), {
      mode: 'dark',
      accent: 'lagoon',
      look: 'classic',
    })
  })

  it('falls back for missing, malformed, or non-object values', () => {
    for (const value of [null, '', 'not json', '"dark"', 'null', '42'])
      assert.deepEqual(parseTheme(value), defaultTheme)
  })

  it('defaults to Classic', () => {
    assert.equal(defaultTheme.look, 'classic')
  })
})

describe('theme storage', () => {
  it('round-trips a saved theme', () => {
    const saved = new Map<string, string>()
    useStorage({
      getItem: (key: string) => saved.get(key) ?? null,
      setItem: (key: string, value: string) => saved.set(key, value),
    })
    saveTheme({ mode: 'light', accent: 'orchid', look: 'console' })
    assert.ok(saved.has(themeStorageKey))
    assert.deepEqual(loadTheme(), {
      mode: 'light',
      accent: 'orchid',
      look: 'console',
    })
  })

  it('tolerates unavailable storage', () => {
    useStorage({
      getItem: () => {
        throw new Error('blocked')
      },
      setItem: () => {
        throw new Error('blocked')
      },
    })
    assert.deepEqual(loadTheme(), defaultTheme)
    assert.doesNotThrow(() => saveTheme(defaultTheme))
  })
})
