import type { View } from './ChatSidebar'

export function LibraryTabs({
  view,
  readyCount,
  onView,
}: {
  view: View
  readyCount: number
  onView: (view: View) => void
}) {
  // Guided demos and the Made in this Lab list sit one step inside Browse and
  // My agents, so those tabs stay current while you are on them.
  const tabs: {
    view: View
    label: string
    count?: number
    hint?: string
    covers: View[]
  }[] = [
    { view: 'library', label: 'Browse', covers: ['library', 'explore'] },
    {
      view: 'catalog',
      label: 'My agents',
      count: readyCount,
      hint: 'Agents you can open in Chat now: prebuilt agents and ones made in this Lab. Library previews are under Browse.',
      covers: ['catalog', 'created'],
    },
    { view: 'addons', label: 'Add-ons', covers: ['addons'] },
  ]
  return (
    <nav className="library-switch" aria-label="Agent library">
      {tabs.map((tab) => (
        <button
          key={tab.view}
          type="button"
          title={tab.hint}
          aria-current={tab.covers.includes(view) ? 'page' : undefined}
          onClick={() => onView(tab.view)}
        >
          {tab.label}
          {tab.count !== undefined && <small>{tab.count}</small>}
        </button>
      ))}
    </nav>
  )
}
