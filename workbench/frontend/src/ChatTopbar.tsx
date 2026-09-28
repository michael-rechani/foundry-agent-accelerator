import {
  ArrowDownToLine,
  ChevronRight,
  Info,
  LoaderCircle,
  Presentation,
  Save,
} from 'lucide-react'
import { AgentGuide, AgentRuntime } from './AgentGuide'
import { AgentSwitcher, type SwitcherOption } from './AgentSwitcher'
import type { View } from './ChatSidebar'
import { crumbs, libraryViews } from './navigation'
import { ThemePicker } from './ThemePicker'
import type { Agent, Config } from './workspace-config'

export function ChatTopbar({
  view,
  detail,
  config,
  agent,
  selected,
  readyOptions,
  previewOptions,
  previewNote,
  switchDisabled,
  isPreview,
  saving,
  saveDisabled,
  saveNote,
  exportDisabled,
  presenting,
  onPresent,
  onView,
  onChoose,
  onSave,
  onExport,
}: {
  view: View
  detail?: string
  config: Config | null
  agent?: Agent
  selected: string
  readyOptions: SwitcherOption[]
  previewOptions: SwitcherOption[]
  previewNote: string
  switchDisabled: boolean
  isPreview: boolean
  saving: boolean
  saveDisabled: boolean
  saveNote?: string
  exportDisabled: boolean
  presenting: boolean
  onPresent: () => void
  onView: (view: View) => void
  onChoose: (id: string) => void
  onSave: () => void
  onExport: () => void
}) {
  return (
    <header className="chat-topbar">
      {view !== 'chat' && (
        <nav className="topbar-crumbs" aria-label="Breadcrumb">
          <ol>
            <li>
              {libraryViews.includes(view) && view !== 'library' && !detail ? (
                <button type="button" onClick={() => onView('library')}>
                  {crumbs[view][0]}
                </button>
              ) : (
                <span>{crumbs[view][0]}</span>
              )}
              <ChevronRight size={14} aria-hidden="true" />
            </li>
            <li aria-current="page">{detail || crumbs[view][1]}</li>
          </ol>
        </nav>
      )}
      {view === 'chat' && (
        <div className="agent-controls">
          <AgentSwitcher
            label={
              agent?.label ||
              (selected.startsWith('created-')
                ? 'Agent unavailable'
                : config
                  ? 'Loading agent'
                  : 'Connecting')
            }
            selected={selected}
            ready={readyOptions}
            previews={previewOptions}
            previewNote={previewNote}
            disabled={!config || switchDisabled}
            onChoose={onChoose}
            onBrowse={() => onView('library')}
          />
          {agent && (
            <details
              className="agent-about"
              name="topbar-panel"
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
                  {isPreview
                    ? 'Library preview: the Lab runs this definition on its model with sample lookups only. Nothing is published, and preview chats are not saved.'
                    : 'This agent already has a published setup. Your message gives it a task; it does not change its tools or permanent instructions.'}
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
        <button
          className="chat-icon presenter-toggle"
          title="Presenter view"
          aria-label="Presenter view"
          aria-pressed={presenting}
          onClick={onPresent}
        >
          <Presentation size={18} />
        </button>
        {config?.mode === 'private' ? (
          <details
            className="lab-info"
            name="topbar-panel"
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
              <p>Use sample data only.</p>
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
              className="topbar-button"
              title={saveNote || 'Save to shared history'}
              aria-label="Save to shared history"
              aria-describedby={
                config?.mode === 'private' ? 'chat-privacy' : undefined
              }
              disabled={saveDisabled}
              onClick={onSave}
            >
              {saving ? (
                <LoaderCircle size={17} className="spin" />
              ) : (
                <Save size={16} />
              )}
              <span>Save</span>
            </button>
            <button
              className="topbar-button"
              title="Export conversation"
              aria-label="Export conversation"
              disabled={exportDisabled}
              onClick={onExport}
            >
              <ArrowDownToLine size={16} />
              <span>Export</span>
            </button>
          </>
        )}
        <ThemePicker />
      </div>
    </header>
  )
}
