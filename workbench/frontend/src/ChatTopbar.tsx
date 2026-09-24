import {
  ArrowDownToLine,
  ChevronDown,
  Info,
  LoaderCircle,
  Save,
} from 'lucide-react'
import { AgentGuide, AgentRuntime } from './AgentGuide'
import type { View } from './ChatSidebar'
import { ThemePicker } from './ThemePicker'
import type { Agent, Config } from './workspace-config'

export function ChatTopbar({
  view,
  config,
  agent,
  selected,
  saving,
  saveDisabled,
  exportDisabled,
  onView,
  onSave,
  onExport,
}: {
  view: View
  config: Config | null
  agent?: Agent
  selected: string
  saving: boolean
  saveDisabled: boolean
  exportDisabled: boolean
  onView: (view: View) => void
  onSave: () => void
  onExport: () => void
}) {
  return (
    <header className="chat-topbar">
      {view === 'chat' && (
        <div className="agent-controls">
          <button
            className="agent-picker"
            title="Choose an agent"
            disabled={!config}
            onClick={() => onView('catalog')}
          >
            <span className="agent-name">
              {agent?.label ||
                (selected.startsWith('created-')
                  ? 'Agent unavailable'
                  : 'Connecting')}
            </span>
            <ChevronDown size={14} aria-hidden="true" />
          </button>
          {agent && (
            <details
              className="agent-about"
              key={agent.id}
              onKeyDown={(event) => {
                if (event.key === 'Escape') event.currentTarget.open = false
              }}
            >
              <summary>About this agent</summary>
              <aside
                className="agent-info-panel"
                aria-label="Selected agent guide"
              >
                <h2>{agent.label}</h2>
                <p>{agent.description}</p>
                <AgentGuide agent={agent} />
                <p>
                  This agent already has a published setup. Your message gives
                  it a task; it does not change its tools or permanent
                  instructions.
                </p>
                <AgentRuntime agent={agent} />
                <button
                  className="inline-link"
                  onClick={() => onView('catalog')}
                >
                  Choosing or changing an agent
                </button>
              </aside>
            </details>
          )}
        </div>
      )}
      <div className="topbar-actions">
        {config?.mode === 'private' ? (
          <details
            className="lab-info"
            key={view}
            onKeyDown={(event) => {
              if (event.key === 'Escape') event.currentTarget.open = false
            }}
          >
            <summary
              className="environment-badge private"
              title="About this shared lab"
            >
              <span className="status-dot" />
              Shared lab
              <Info size={13} aria-hidden="true" />
            </summary>
            <aside className="lab-info-panel" aria-label="Shared lab details">
              <strong>Private shared lab</strong>
              <p>No user sign-in. Saved records are shared.</p>
              <p>Use synthetic data only.</p>
              <p>
                Everyone with workspace access can read, modify and delete saved
                chats, and read reviews and add requested evidence. There is no
                per-user authorization; private networking does not isolate
                users.
              </p>
              {config.agent_creation && (
                <p>
                  Created-agent setups are shared too. Publishing or deleting a
                  created agent requires an operator key, not an individual user
                  account.
                </p>
              )}
            </aside>
          </details>
        ) : (
          <span className="environment-badge" title="No model calls or saving">
            <span className="status-dot" />
            {config ? 'Local preview' : 'Connecting'}
          </span>
        )}
        {view === 'chat' && (
          <>
            <button
              className="chat-icon"
              title="Save to shared history"
              aria-label="Save to shared history"
              disabled={saveDisabled}
              onClick={onSave}
            >
              {saving ? (
                <LoaderCircle size={17} className="spin" />
              ) : (
                <Save size={17} />
              )}
            </button>
            <button
              className="chat-icon"
              title="Export conversation"
              aria-label="Export conversation"
              disabled={exportDisabled}
              onClick={onExport}
            >
              <ArrowDownToLine size={17} />
            </button>
          </>
        )}
        <ThemePicker />
      </div>
    </header>
  )
}
