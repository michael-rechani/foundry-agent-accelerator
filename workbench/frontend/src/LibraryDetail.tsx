import {
  ArrowLeft,
  ArrowRight,
  Construction,
  MessageSquare,
  UserCheck,
} from 'lucide-react'
import type { LibraryTemplate } from './library-catalog'
import { Badges } from './LibraryBadges'
import { LibraryExportTab } from './LibraryExportTab'
import {
  inProgress,
  runTemplateChat,
  storesOpenChat,
  type LibraryTab,
  type ReadyAgent,
} from './library-helpers'
import { LibraryOverviewTab } from './LibraryOverviewTab'
import { LibraryTryTab } from './LibraryTryTab'
import { ScorecardPanel } from './ScorecardPanel'
import type { ScorecardsState } from './scorecards-client'
import { tabKeyDown } from './tab-keys'
import type { Agent, CreationCapability } from './workspace-config'

const tabs: [LibraryTab, string][] = [
  ['overview', 'Overview'],
  ['test', 'Try it'],
  ['results', 'Test results'],
  ['export', 'Take it to Foundry'],
]
const tabIds = tabs.map(([id]) => id)

export function LibraryDetail({
  template,
  tab,
  scorecards,
  capability,
  foundryPortal,
  ready,
  preview,
  busy,
  notice,
  onTab,
  onBack,
  onCreate,
  onTest,
  onNotice,
}: {
  template: LibraryTemplate
  tab: LibraryTab
  scorecards: ScorecardsState
  capability?: CreationCapability
  foundryPortal?: string | null
  ready?: ReadyAgent
  preview?: Agent
  busy: boolean
  notice: string
  onTab: (tab: LibraryTab) => void
  onBack: () => void
  onCreate: () => void
  onTest: (agent: Agent, input: string) => void
  onNotice: (text: string) => void
}) {
  const opensChat = storesOpenChat(template, preview, ready)

  function tryIt() {
    if (opensChat) runTemplateChat(template, preview, ready, onTest)
    else onTab('test')
  }

  return (
    <article className="library-detail" aria-labelledby="library-detail-title">
      <button type="button" className="library-back" onClick={onBack}>
        <ArrowLeft size={16} /> Back to all agents
      </button>
      <div className="library-badges">
        <span className="library-badge">{template.industry.label}</span>
        <Badges template={template} />
        <span className="library-badge hood-only">{template.sector.label}</span>
        {template.tasks.map((task) => (
          <span key={task.id} className="library-badge hood-only">
            {task.label}
          </span>
        ))}
      </div>
      <h1 id="library-detail-title">{template.label}</h1>
      <p className="library-lede">{template.summary}</p>
      <div className="library-actions library-hero-actions">
        <button
          type="button"
          className="library-primary"
          disabled={busy}
          onClick={tryIt}
        >
          <MessageSquare size={16} />{' '}
          {opensChat ? 'Try it in Chat' : 'Try it with an example'}
        </button>
        <button
          type="button"
          className="library-secondary"
          onClick={() => onTab('export')}
        >
          Take it to Foundry <ArrowRight size={16} />
        </button>
      </div>
      {inProgress(template) && (
        <div className="library-progress" role="note">
          <Construction size={18} aria-hidden="true" />
          <p>
            <strong>In progress. </strong>A person hasn&apos;t signed off on its
            test answers yet. Try it with sample data; answers may change.
          </p>
        </div>
      )}
      <div className="library-decision" role="note">
        <UserCheck size={18} aria-hidden="true" />
        <p>
          <strong>A person decides. </strong>
          {template.human_decision}
        </p>
      </div>
      <div className="library-tabs" role="tablist" aria-label="Agent details">
        {tabs.map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`library-tab-${id}`}
            aria-selected={tab === id}
            aria-controls="library-tabpanel"
            tabIndex={tab === id ? 0 : -1}
            onClick={() => onTab(id)}
            onKeyDown={(event) => tabKeyDown(event, tabIds, id, onTab)}
          >
            {label}
          </button>
        ))}
      </div>
      {notice && (
        <p className="library-notice" role="status">
          {notice}
        </p>
      )}
      <div
        className="library-tabpanel"
        id="library-tabpanel"
        role="tabpanel"
        aria-labelledby={`library-tab-${tab}`}
      >
        {tab === 'overview' && <LibraryOverviewTab template={template} />}
        {tab === 'test' && (
          <LibraryTryTab
            template={template}
            capability={capability}
            ready={ready}
            preview={preview}
            busy={busy}
            onCreate={onCreate}
            onTest={onTest}
            onNotice={onNotice}
          />
        )}
        {tab === 'results' && (
          <ScorecardPanel templateId={template.id} state={scorecards} />
        )}
        {tab === 'export' && (
          <LibraryExportTab
            template={template}
            scorecards={scorecards}
            capability={capability}
            foundryPortal={foundryPortal}
            ready={ready}
            busy={busy}
            onCreate={onCreate}
            onNotice={onNotice}
          />
        )}
      </div>
    </article>
  )
}
