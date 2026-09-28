import type { View } from './ChatSidebar'

export function LibraryTabs({
  view,
  readyCount,
  createdCount,
  creationEnabled,
  onView,
  onCreated,
}: {
  view: View
  readyCount: number
  createdCount: number
  creationEnabled: boolean
  onView: (view: View) => void
  onCreated: () => void
}) {
  const tabs: { view: View; label: string; count?: number }[] = [
    { view: 'library', label: 'Templates' },
    { view: 'catalog', label: 'Ready to use', count: readyCount },
    ...(creationEnabled
      ? [
          {
            view: 'created' as const,
            label: 'Created here',
            count: createdCount,
          },
        ]
      : []),
    { view: 'explore', label: 'Guided demos' },
  ]
  return (
    <nav className="library-switch" aria-label="Agent library">
      {tabs.map((tab) => (
        <button
          key={tab.view}
          type="button"
          aria-current={view === tab.view ? 'page' : undefined}
          onClick={tab.view === 'created' ? onCreated : () => onView(tab.view)}
        >
          {tab.label}
          {tab.count !== undefined && <small>{tab.count}</small>}
        </button>
      ))}
    </nav>
  )
}
