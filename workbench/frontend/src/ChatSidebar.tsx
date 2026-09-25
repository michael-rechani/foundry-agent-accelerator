import {
  Activity,
  Compass,
  FileCheck2,
  History,
  Layers3,
  LayoutGrid,
  MessageSquare,
  Plus,
} from 'lucide-react'

export type View =
  | 'explore'
  | 'chat'
  | 'catalog'
  | 'performance'
  | 'history'
  | 'reviews'
  | 'create'
  | 'created'

export function ChatSidebar({
  title,
  view,
  creationEnabled,
  historyEnabled,
  busy,
  historyBusy,
  agentCount,
  onNewChat,
  onView,
  onCreatedAgents,
  onHistory,
}: {
  title?: string
  view: View
  creationEnabled: boolean
  historyEnabled: boolean
  busy: boolean
  historyBusy: boolean
  agentCount: number
  onNewChat: () => void
  onView: (view: View) => void
  onCreatedAgents: () => void
  onHistory: () => void
}) {
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
        <button
          aria-current={view === 'explore' ? 'page' : undefined}
          onClick={() => onView('explore')}
          title="Explore demos"
        >
          <Compass size={18} />
          <span>Explore demos</span>
        </button>
        {creationEnabled && (
          <>
            <button
              aria-current={view === 'create' ? 'page' : undefined}
              onClick={() => onView('create')}
              title="Create agent"
            >
              <Plus size={18} />
              <span>Create agent</span>
            </button>
            <button
              aria-current={view === 'created' ? 'page' : undefined}
              onClick={onCreatedAgents}
              title="Created agents"
            >
              <Layers3 size={18} />
              <span>Created agents</span>
            </button>
          </>
        )}
        <button
          aria-current={view === 'chat' ? 'page' : undefined}
          onClick={() => onView('chat')}
          title="Chat"
        >
          <MessageSquare size={18} />
          <span>Chat</span>
        </button>
        <button
          aria-current={view === 'reviews' ? 'page' : undefined}
          onClick={() => onView('reviews')}
          title="Document reviews"
        >
          <FileCheck2 size={18} />
          <span>Document reviews</span>
        </button>
        <button
          disabled={!historyEnabled || historyBusy}
          aria-current={view === 'history' ? 'page' : undefined}
          onClick={onHistory}
          title="Shared history"
        >
          <History size={18} />
          <span>Shared history</span>
        </button>
        <button
          aria-current={view === 'catalog' ? 'page' : undefined}
          onClick={() => onView('catalog')}
          title="Agent catalog"
        >
          <LayoutGrid size={18} />
          <span>Agent catalog</span>
          <small>{agentCount}</small>
        </button>
        <button
          aria-current={view === 'performance' ? 'page' : undefined}
          onClick={() => onView('performance')}
          title="Performance"
        >
          <Activity size={18} />
          <span>Performance</span>
        </button>
      </nav>
    </aside>
  )
}
