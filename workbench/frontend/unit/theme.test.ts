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
  it('accepts a saved mode and accent', () => {
    assert.deepEqual(parseTheme('{"mode":"dark","accent":"lagoon"}'), {
      mode: 'dark',
      accent: 'lagoon',
    })
  })

  it('replaces each unknown field independently', () => {
    assert.deepEqual(parseTheme('{"mode":"sepia","accent":"orchid"}'), {
      mode: defaultTheme.mode,
      accent: 'orchid',
    })
    assert.deepEqual(parseTheme('{"mode":"light","accent":7}'), {
      mode: 'light',
      accent: defaultTheme.accent,
    })
  })

  it('falls back for missing, malformed, or non-object values', () => {
    for (const value of [null, '', 'not json', '"dark"', 'null', '42'])
      assert.deepEqual(parseTheme(value), defaultTheme)
  })
})

describe('theme storage', () => {
  it('round-trips a saved theme', () => {
    const saved = new Map<string, string>()
    useStorage({
      getItem: (key: string) => saved.get(key) ?? null,
      setItem: (key: string, value: string) => saved.set(key, value),
    })
    saveTheme({ mode: 'light', accent: 'orchid' })
    assert.ok(saved.has(themeStorageKey))
    assert.deepEqual(loadTheme(), { mode: 'light', accent: 'orchid' })
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
