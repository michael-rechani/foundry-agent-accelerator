import type { KeyboardEvent } from 'react'

// Arrow keys move around a tab list and wrap at the ends; Home and End jump to
// the first and last tab.
const moves = {
  ArrowRight: (index: number, count: number) => (index + 1) % count,
  ArrowLeft: (index: number, count: number) => (index + count - 1) % count,
  Home: () => 0,
  End: (_index: number, count: number) => count - 1,
}

// Keyboard handling for the ARIA tabs pattern with automatic activation. Put it
// on every tab in a tablist. Moving to a tab also selects it, so only the
// selected tab needs tabIndex 0 (roving tabindex) and the others -1.
export function tabKeyDown<T extends string>(
  event: KeyboardEvent<HTMLElement>,
  ids: readonly T[],
  current: T,
  select: (id: T) => void,
) {
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
  const move = moves[event.key as keyof typeof moves]
  if (!move) return
  const tabs = event.currentTarget
    .closest('[role="tablist"]')
    ?.querySelectorAll<HTMLElement>('[role="tab"]')
  if (tabs?.length !== ids.length) return
  const index = move(ids.indexOf(current), ids.length)
  event.preventDefault()
  tabs[index].focus()
  select(ids[index])
}
