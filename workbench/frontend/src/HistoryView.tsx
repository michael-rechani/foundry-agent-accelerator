import { MessageSquare, Trash2 } from 'lucide-react'
import type { Agent } from './workspace-config'

export type SavedChat = {
  id: string
  title: string
  agent_id: string
  updated_at: string
}

export function HistoryView({
  chats,
  agents,
  retentionDays,
  cursor,
  busy,
  historyBusy,
  onOpen,
  onDelete,
  onMore,
}: {
  chats: SavedChat[]
  agents: Agent[]
  retentionDays?: number
  cursor: string | null
  busy: boolean
  historyBusy: boolean
  onOpen: (item: SavedChat) => void
  onDelete: (item: SavedChat) => void
  onMore: () => void
}) {
  return (
    <main className="secondary-view">
      <div className="section-heading">
        <h1>Saved conversations</h1>
        <p>
          Everyone with workspace access can read, modify and delete saved
          conversations. Expires {retentionDays} days after the last update.
        </p>
      </div>
      <div className="saved-list">
        {chats.map((item) => (
          <article key={item.id}>
            <button
              className="saved-open"
              disabled={busy || historyBusy}
              onClick={() => onOpen(item)}
            >
              <MessageSquare size={18} />
              <span>
                <strong>{item.title}</strong>
                <small>
                  {agents.find((entry) => entry.id === item.agent_id)?.label} /{' '}
                  {new Date(item.updated_at).toLocaleString()}
                </small>
              </span>
            </button>
            <button
              className="chat-icon"
              title="Delete shared conversation"
              aria-label={`Delete ${item.title}`}
              disabled={busy || historyBusy}
              onClick={() => onDelete(item)}
            >
              <Trash2 size={16} />
            </button>
          </article>
        ))}
      </div>
      {historyBusy ? (
        <p role="status">Loading history...</p>
      ) : !chats.length ? (
        <p className="no-data">No saved conversations</p>
      ) : null}
      {cursor && (
        <button
          className="history-more"
          disabled={historyBusy}
          onClick={onMore}
        >
          Load more
        </button>
      )}
    </main>
  )
}
