import {
  ArrowDownToLine,
  ChevronRight,
  LoaderCircle,
  Plus,
  Presentation,
  Save,
} from 'lucide-react'
import { AgentGuide, AgentRuntime } from './AgentGuide'
import { AgentSwitcher, type SwitcherOption } from './AgentSwitcher'
import type { View } from './ChatSidebar'
import { crumbs, libraryViews } from './navigation'
import {
  createFromPreviewNote,
  previewBlurb,
  publishedBlurb,
} from './library-helpers'
import { ThemePicker } from './ThemePicker'
import type { Agent, Config } from './workspace-config'

export function ChatTopbar({
  view,
  detail,
  config,
  agent,
  selected,
  generalOptions = [],
  readyOptions,
  previewOptions,
  previewNote,
  switchDisabled,
  switcherOpen,
  isPreview,
  saving,
  saveDisabled,
  saveNote,
  exportDisabled,
  presenting,
  clean = false,
  started = false,
  onPresent,
  onView,
  onSwitcherOpen,
  onChoose,
  onSave,
  onExport,
  onCreateThis,
}: {
  view: View
  detail?: string
  config: Config | null
  agent?: Agent
  selected: string
  generalOptions?: SwitcherOption[]
  readyOptions: SwitcherOption[]
  previewOptions: SwitcherOption[]
  previewNote: string
  switchDisabled: boolean
  switcherOpen: boolean
  isPreview: boolean
  saving: boolean
  saveDisabled: boolean
  saveNote?: string
  exportDisabled: boolean
  presenting: boolean
  // The first screen is not about one agent yet, so agent details and the
  // save and export actions are left out.
  clean?: boolean
  // The conversation has begun, so the picker names who is answering.
  started?: boolean
  onPresent: () => void
  onView: (view: View) => void
  onSwitcherOpen: (open: boolean) => void
  onChoose: (id: string) => void
  onSave: () => void
  onExport: () => void
  // Only for a library preview where creating agents is possible. It takes
  // the place of Save, which a preview never offers.
  onCreateThis?: () => void
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
              clean && !(started && agent)
                ? 'Choose an agent'
                : agent?.label ||
                  (selected.startsWith('created-')
                    ? 'Agent unavailable'
                    : config
                      ? 'Loading agent'
                      : 'Connecting')
            }
            selected={selected}
            general={generalOptions}
            ready={readyOptions}
            previews={previewOptions}
            previewNote={previewNote}
            disabled={!config || switchDisabled}
            open={switcherOpen}
            onOpenChange={onSwitcherOpen}
            onChoose={onChoose}
            onBrowse={() => onView('library')}
          />
          {agent && isPreview && !clean && (
            <span className="agent-preview-badge" title={previewBlurb}>
              Library preview
            </span>
          )}
          {agent && !clean && (
            // oxlint-disable-next-line jsx-a11y/no-noninteractive-element-interactions -- Escape bubbles up from the summary and controls inside this disclosure.
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
                <p>{isPreview ? previewBlurb : publishedBlurb}</p>
                <AgentRuntime
                  agent={agent}
                  foundryPortal={isPreview ? null : config?.foundry_portal}
                />
                <button
                  className="inline-link"
                  onClick={() => onView('catalog')}
                >
                  Change agent
                </button>
              </aside>
            </details>
          )}
        </div>
      )}
      <div className="topbar-actions">
        {!clean && (
          <button
            className="chat-icon presenter-toggle"
            title="Presenter view"
            aria-label="Presenter view"
            aria-pressed={presenting}
            onClick={onPresent}
          >
            <Presentation size={18} />
          </button>
        )}
        {config?.mode !== 'private' && !(clean && config) && (
          <span className="environment-badge" title="No model calls or saving">
            <span className="status-dot" />
            {config ? 'Local preview' : 'Connecting'}
          </span>
        )}
        {view === 'chat' && !clean && (
          <>
            {onCreateThis ? (
              <button
                className="topbar-button"
                title={createFromPreviewNote}
                aria-label="Create this agent"
                onClick={onCreateThis}
              >
                <Plus size={16} />
                <span>Create this agent</span>
              </button>
            ) : (
              <button
                className="topbar-button"
                title={
                  saveNote ||
                  'Save to shared history. Everyone who uses this Lab can open it.'
                }
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
                <span>Save to shared history</span>
              </button>
            )}
            <button
              className="topbar-button"
              title="Export conversation. Downloads a file to your computer and shares nothing."
              aria-label="Export conversation"
              disabled={exportDisabled}
              onClick={onExport}
            >
              <ArrowDownToLine size={16} />
              <span>Export conversation</span>
            </button>
          </>
        )}
        <ThemePicker />
      </div>
    </header>
  )
}
