import { useEffect, useState } from 'react'
import type { View } from './ChatSidebar'
import { reviewIdFromHash } from './review-client'
import type { Config } from './workspace-config'

const hashViews: Record<string, View> = {
  '#start': 'start',
  '#chat': 'chat',
  '#create': 'create',
  '#library': 'library',
  '#agents': 'catalog',
  '#demos': 'explore',
  '#addons': 'addons',
  '#operations': 'operations',
  '#reviews': 'reviews',
  '#performance': 'performance',
  '#logs': 'log',
}

const viewForHash = (hash: string): View | null =>
  reviewIdFromHash(hash) ? 'reviews' : (hashViews[hash] ?? null)

// The page being shown. It follows the URL hash and opens on Chat when there is
// none. Create agent falls back to the library in a Lab that cannot create
// agents.
export function useChatView(config: Config | null) {
  const [selectedView, setView] = useState<View | null>(() =>
    viewForHash(window.location.hash),
  )
  useEffect(() => {
    const follow = () => {
      const next = viewForHash(window.location.hash)
      if (next) setView(next)
    }
    window.addEventListener('hashchange', follow)
    return () => window.removeEventListener('hashchange', follow)
  }, [])
  const view: View =
    selectedView === 'create' && config && !config.agent_creation
      ? 'library'
      : (selectedView ?? 'chat')
  return { view, setView }
}
