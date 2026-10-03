import { useState } from 'react'
import type { LibraryViewMode } from './library-helpers'

const libraryViewStorageKey = 'foundry-lab-library-view'

function readLibraryView(): LibraryViewMode {
  if (typeof window === 'undefined') return 'cards'
  try {
    return window.localStorage.getItem(libraryViewStorageKey) === 'list'
      ? 'list'
      : 'cards'
  } catch {
    return 'cards'
  }
}

// The cards or list choice, remembered between visits.
export function useLibraryViewMode() {
  const [viewMode, setViewMode] = useState<LibraryViewMode>(readLibraryView)

  function setLibraryView(next: LibraryViewMode) {
    setViewMode(next)
    try {
      window.localStorage.setItem(libraryViewStorageKey, next)
    } catch {}
  }

  return [viewMode, setLibraryView] as const
}
