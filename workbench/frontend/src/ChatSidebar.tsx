import {
  Activity,
  BookOpen,
  FileCheck2,
  History,
  Layers3,
  MessageSquare,
  Plus,
  ScrollText,
  type LucideIcon,
} from 'lucide-react'
import { libraryViews } from './navigation'

export type View =
  | 'library'
  | 'explore'
  | 'chat'
  | 'catalog'
  | 'performance'
  | 'log'
  | 'history'
  | 'reviews'
  | 'create'
  | 'created'

export type Section = 'test' | 'library' | 'performance' | 'logging'

type Item = {
  view: View
  label: string
  icon: LucideIcon
  enabled?: boolean
  count?: number
  current?: boolean
  onSelect?: () => void
}

const sectionOf: Record<View, Section> = {
  chat: 'test',
  reviews: 'test',
  history: 'test',
  explore: 'library',
  library: 'library',
  catalog: 'library',
  create: 'library',
  created: 'library',
  performance: 'performance',
  log: 'logging',
}

export function ChatSidebar({
  title,
  view,
  creationEnabled,
  historyEnabled,
  busy,
  historyBusy,
  requestCount,
  onNewChat,
  onView,
  onHistory,
}: {
  title?: string
  view: View
  creationEnabled: boolean
  historyEnabled: boolean
  busy: boolean
  historyBusy: boolean
  requestCount: number
  onNewChat: () => void
  onView: (view: View) => void
  onHistory: () => void
}) {
  const sections: { id: Section; label: string; items: Item[] }[] = [
    {
      id: 'test',
      label: 'Chat and test',
      items: [
        { view: 'chat', label: 'Chat', icon: MessageSquare },
        // Reviews are reached only from /#reviews or a saved-review link.
        ...(view === 'reviews'
          ? [
              {
                view: 'reviews' as const,
                label: 'Document reviews',
                icon: FileCheck2,
              },
            ]
          : []),
        {
          view: 'history',
          label: 'Shared history',
          icon: History,
          enabled: historyEnabled && !historyBusy,
          onSelect: onHistory,
        },
      ],
    },
    {
      id: 'library',
      label: 'Agent library',
      items: [
        {
          view: 'library',
          label: 'All agents',
          icon: BookOpen,
          current: libraryViews.includes(view),
        },
        ...(creationEnabled
          ? [{ view: 'create' as const, label: 'Create agent', icon: Plus }]
          : []),
      ],
    },
    {
      id: 'performance',
      label: 'Performance and benchmarking',
      items: [{ view: 'performance', label: 'Performance', icon: Activity }],
    },
    {
      id: 'logging',
      label: 'Logging',
      items: [
        {
          view: 'log',
          label: 'Request log',
          icon: ScrollText,
          count: requestCount,
        },
      ],
    },
  ]
  const current = sectionOf[view]
  return (
    <aside className="chat-sidebar">
      <div className="chat-brand">
        <span className="brand-mark" aria-hidden="true">
          <Layers3 size={23} />
        </span>
        <span>{title || 'Foundry Agent Lab'}</span>
      </div>
      {view === 'chat' && (
        <button
          className="new-chat"
          disabled={busy || historyBusy}
          onClick={onNewChat}
          title="New chat"
        >
          <Plus size={18} />
          <span>New chat</span>
        </button>
      )}
      <nav aria-label="Workspace">
        {sections.map((section) => (
          <div
            key={section.id}
            className="nav-section"
            role="group"
            aria-labelledby={`nav-section-${section.id}`}
            data-active={current === section.id ? 'true' : undefined}
          >
            <div className="nav-section-label" id={`nav-section-${section.id}`}>
              {section.label}
            </div>
            {section.items.map((item) => {
              const Icon = item.icon
              return (
                <button
                  key={item.view}
                  disabled={item.enabled === false}
                  aria-current={
                    (item.current ?? view === item.view) ? 'page' : undefined
                  }
                  onClick={item.onSelect ?? (() => onView(item.view))}
                  title={item.label}
                >
                  <Icon size={18} />
                  <span>{item.label}</span>
                  {item.count !== undefined && <small>{item.count}</small>}
                </button>
              )
            })}
          </div>
        ))}
      </nav>
    </aside>
  )
}
