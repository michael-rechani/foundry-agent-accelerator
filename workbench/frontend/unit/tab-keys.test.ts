import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { KeyboardEvent } from 'react'
import { tabKeyDown } from '../src/tab-keys.ts'

const ids = ['overview', 'test', 'results', 'export'] as const
type Id = (typeof ids)[number]

function press(
  key: string,
  current: Id,
  modifiers: { shiftKey?: boolean; ctrlKey?: boolean } = {},
  tabCount = ids.length,
) {
  const focused: number[] = []
  const selected: Id[] = []
  const tabs = Array.from({ length: tabCount }, (_, index) => ({
    focus: () => focused.push(index),
  }))
  let prevented = false
  const event = {
    key,
    altKey: false,
    ctrlKey: false,
    metaKey: false,
    shiftKey: false,
    ...modifiers,
    preventDefault: () => (prevented = true),
    currentTarget: {
      closest: () => ({ querySelectorAll: () => tabs }),
    },
  } as unknown as KeyboardEvent<HTMLElement>
  tabKeyDown(event, ids, current, (id) => selected.push(id))
  return { focused, selected, prevented }
}

describe('tabKeyDown', () => {
  it('moves to the next and previous tab and wraps at the ends', () => {
    assert.deepEqual(press('ArrowRight', 'overview').selected, ['test'])
    assert.deepEqual(press('ArrowRight', 'export').selected, ['overview'])
    assert.deepEqual(press('ArrowLeft', 'test').selected, ['overview'])
    assert.deepEqual(press('ArrowLeft', 'overview').selected, ['export'])
  })

  it('moves focus to the tab it selects', () => {
    const result = press('ArrowRight', 'test')
    assert.deepEqual(result.focused, [2])
    assert.deepEqual(result.selected, ['results'])
    assert.equal(result.prevented, true)
  })

  it('jumps to the first and last tab with Home and End', () => {
    assert.deepEqual(press('Home', 'results').selected, ['overview'])
    assert.deepEqual(press('End', 'results').selected, ['export'])
    assert.deepEqual(press('Home', 'results').focused, [0])
    assert.deepEqual(press('End', 'results').focused, [3])
  })

  it('leaves other keys and modified keys to the browser', () => {
    for (const result of [
      press('Enter', 'test'),
      press('ArrowDown', 'test'),
      press('Tab', 'test'),
      press('ArrowRight', 'test', { ctrlKey: true }),
      press('ArrowLeft', 'test', { shiftKey: true }),
    ]) {
      assert.deepEqual(result.selected, [])
      assert.deepEqual(result.focused, [])
      assert.equal(result.prevented, false)
    }
  })

  it('does nothing when the tab list does not match the tabs', () => {
    const result = press('ArrowRight', 'test', {}, ids.length + 1)
    assert.deepEqual(result.selected, [])
    assert.equal(result.prevented, false)
  })
})
