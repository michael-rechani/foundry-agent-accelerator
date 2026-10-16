import {
  Activity,
  BookOpen,
  FileCheck2,
  History,
  Layers3,
  MessageCircleQuestion,
  MessageSquare,
  Plus,
  ScrollText,
  type LucideIcon,
} from 'lucide-react'
import { FoundryLink } from './FoundryLink'
import { libraryViews } from './navigation'

export type View =
  | 'start'
  | 'library'
  | 'explore'
  | 'addons'
  | 'chat'
  | 'catalog'
  | 'operations'
  | 'performance'
  | 'log'
  | 'history'
  | 'reviews'
  | 'create'
  | 'created'

export type Section = 'start' | 'test' | 'library' | 'operations'

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
  start: 'start',
  chat: 'test',
  reviews: 'test',
  history: 'test',
  explore: 'library',
  addons: 'library',
  library: 'library',
  catalog: 'library',
  create: 'library',
  created: 'library',
  operations: 'operations',
  performance: 'operations',
  log: 'operations',
}

export function ChatSidebar({
  title,
  view,
  creationEnabled,
  historyEnabled,
  busy,
  historyBusy,
  libraryCount,
  historyCount,
  requestCount,
  hood,
  foundryPortal,
  onNewChat,
  onView,
  onHistory,
  onHood,
}: {
  title?: string
  view: View
  creationEnabled: boolean
  historyEnabled: boolean
  busy: boolean
  historyBusy: boolean
  libraryCount?: number
  historyCount?: number
  requestCount: number
  hood: boolean
  foundryPortal?: string | null
  onNewChat: () => void
  onView: (view: View) => void
  onHistory: () => void
  onHood: (on: boolean) => void
}) {
  const sections: {
    id: Section
    label: string
    items: Item[]
    hood?: boolean
  }[] = [
    {
      id: 'start',
      label: 'Start here',
      items: [
        { view: 'start', label: 'Ask the Lab', icon: MessageCircleQuestion },
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
          count: libraryCount,
          current: libraryViews.includes(view),
        },
        ...(creationEnabled
          ? [{ view: 'create' as const, label: 'Create agent', icon: Plus }]
          : []),
      ],
    },
    {
      id: 'test',
      label: 'Try it',
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
          count: historyCount,
          enabled: historyEnabled && !historyBusy,
          onSelect: onHistory,
        },
      ],
    },
    {
      id: 'operations',
      label: 'Operations',
      hood: true,
      items: [
        { view: 'operations', label: 'Overview', icon: Activity },
        { view: 'performance', label: 'Performance', icon: Activity },
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
      <button
        className="new-chat"
        disabled={busy || historyBusy}
        onClick={onNewChat}
        title="Start a new chat with the selected agent"
      >
        <Plus size={18} />
        <span>New chat</span>
      </button>
      <nav aria-label="Workspace">
        {sections
          .filter((section) => !section.hood || hood || current === section.id)
          .map((section) => (
            <div
              key={section.id}
              className="nav-section"
              role="group"
              aria-labelledby={`nav-section-${section.id}`}
              data-active={current === section.id ? 'true' : undefined}
            >
              <div
                className="nav-section-label"
                id={`nav-section-${section.id}`}
              >
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
      <div className="sidebar-footer">
        {hood && foundryPortal && (
          <FoundryLink href={foundryPortal}>
            Open project in Foundry
          </FoundryLink>
        )}
        <label className="hood-switch">
          <span>
            Under the hood
            <small>
              {hood
                ? 'Showing models, tokens and setup'
                : 'Plain view for customers'}
            </small>
          </span>
          <input
            type="checkbox"
            // oxlint-disable-next-line jsx-a11y/role-has-required-aria-props -- A native checkbox already exposes its checked state to the switch role.
            role="switch"
            checked={hood}
            onChange={(event) => onHood(event.currentTarget.checked)}
          />
        </label>
      </div>
    </aside>
  )
}
