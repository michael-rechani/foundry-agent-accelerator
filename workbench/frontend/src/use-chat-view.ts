import { useCallback, useEffect, useState } from 'react'
import type { View } from './ChatSidebar'
import { viewForHash, viewHashes } from './navigation'
import type { Config } from './workspace-config'

// The page being shown. It follows the URL hash and opens on Chat when there is
// none. Create agent falls back to the library in a Lab that cannot create
// agents.
export function useChatView(config: Config | null) {
  const [selectedView, selectView] = useState<View>(() =>
    viewForHash(window.location.hash),
  )
  useEffect(() => {
    const follow = () => {
      selectView(viewForHash(window.location.hash))
    }
    window.addEventListener('hashchange', follow)
    window.addEventListener('popstate', follow)
    return () => {
      window.removeEventListener('hashchange', follow)
      window.removeEventListener('popstate', follow)
    }
  }, [])
  const unavailable =
    (selectedView === 'create' || selectedView === 'created') &&
    config !== null &&
    !config.agent_creation
  if (unavailable) selectView('library')
  useEffect(() => {
    const linked = viewForHash(window.location.hash)
    if (
      config &&
      !config.agent_creation &&
      (linked === 'create' || linked === 'created')
    )
      window.history.replaceState(null, '', viewHashes.library)
  }, [config, selectedView])
  const setView = useCallback((next: View) => {
    const hash = viewHashes[next]
    if (window.location.hash !== hash) window.history.pushState(null, '', hash)
    selectView(next)
  }, [])
  const view: View = unavailable ? 'library' : selectedView
  return { view, setView }
}
