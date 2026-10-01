import type { ReactNode } from 'react'
import {
  ArrowRight,
  Check,
  LoaderCircle,
  RefreshCw,
  Trash2,
} from 'lucide-react'
import type { Agent } from './workspace-config'
import {
  creationMessage,
  type AgentTemplate,
  type CreatedAgent,
} from './agent-creation-client'

const stages: Record<string, string> = {
  queued: 'Setup saved',
  uploading: 'Publishing runtime code',
  provisioning: 'Waiting for Foundry',
  routing: 'Connecting the agent endpoint',
  ready: 'Ready to try',
  failed: 'Needs operator attention',
  interrupted: 'Outcome needs checking',
  deleting: 'Deleting from Foundry',
  deleted: 'Deletion confirmed',
}
const statuses: Record<CreatedAgent['status'], string> = {
  creating: 'Creating',
  ready: 'Ready to try',
  failed: 'Needs attention',
  interrupted: 'Check outcome',
  deleting: 'Deleting',
  deleted: 'Deleted',
}

export function CreatedAgentList({
  records,
  error,
  onSelect,
  onCreate,
}: {
  records: CreatedAgent[]
  error: string
  onSelect: (record: CreatedAgent) => void
  onCreate: () => void
}) {
  return records.length ? (
    <div className="created-agent-list">
      {records.map((record) => (
        <button
          className="created-agent-row"
          key={record.id}
          onClick={() => onSelect(record)}
        >
          <span>
            <strong>{record.name}</strong>
            <small>{record.template_label || record.template_id}</small>
          </span>
          <span className={`creation-status creation-status-${record.status}`}>
            {statuses[record.status]}
          </span>
          <ArrowRight size={16} />
        </button>
      ))}
    </div>
  ) : (
    !error && (
      <div className="creation-empty">
        <h2>Nothing made in this Lab yet</h2>
        <p>
          Agents you create from a library template appear here, with their
          status. Once one is ready, it also shows up under Ready to chat.
        </p>
        <button className="creation-primary" onClick={onCreate}>
          Create an agent
        </button>
      </div>
    )
  )
}

export function CreatedAgentDetail({
  record,
  templates,
  busy,
  chatBusy,
  operationRunning,
  pollPaused,
  publishEnabled,
  canManage,
  operatorKey,
  onBack,
  onRefresh,
  onUse,
  onOperate,
}: {
  record: CreatedAgent
  templates: AgentTemplate[]
  busy: boolean
  chatBusy: boolean
  operationRunning: boolean
  pollPaused: boolean
  publishEnabled: boolean
  canManage: boolean
  operatorKey: ReactNode
  onBack: () => void
  onRefresh: () => void
  onUse: (agent: Agent) => void
  onOperate: (action: 'resume' | 'delete') => void
}) {
  return (
    <section className="creation-detail" aria-label="Created agent details">
      <button className="inline-link" onClick={onBack}>
        Back to created agents
      </button>
      <h2>{record.name}</h2>
      <div className="creation-actions">
        <span className={`creation-status creation-status-${record.status}`}>
          {statuses[record.status]}
        </span>
        <button
          className="creation-secondary"
          disabled={busy}
          onClick={onRefresh}
        >
          <RefreshCw size={16} />
          Refresh status
        </button>
        {record.agent && (
          <button
            className="creation-primary"
            disabled={chatBusy}
            onClick={() => {
              if (record.agent) onUse(record.agent)
            }}
          >
            <ArrowRight size={16} />
            Try in Chat
          </button>
        )}
      </div>
      {operationRunning && (
        <p role="status" className="creation-progress">
          <LoaderCircle size={18} className="spin" />
          {stages[record.stage] || 'Operation in progress'}
          {pollPaused
            ? ' - automatic checks paused; refresh explicitly.'
            : '. This can take several minutes. You can return to this saved record.'}
        </p>
      )}
      {record.error && (
        <p className="creation-notice">{creationMessage(record.error)}</p>
      )}
      {record.status === 'ready' && (
        <p className="creation-help">
          Foundry reported an active runtime and the route was checked. Send a
          sample in Chat to test the answer; this is not a model-quality
          certification.
        </p>
      )}
      <dl className="creation-runtime">
        <div>
          <dt>Template</dt>
          <dd>
            {record.template_label ||
              templates.find((item) => item.id === record.template_id)?.label ||
              record.template_id}
          </dd>
        </div>
        <div>
          <dt>Foundry agent name</dt>
          <dd>
            <code>{record.runtime_name}</code>
          </dd>
        </div>
        <div>
          <dt>Version</dt>
          <dd>{record.version || 'Not confirmed yet'}</dd>
        </div>
        {record.model && (
          <div>
            <dt>Model deployment</dt>
            <dd>
              <code>{record.model}</code>
              {record.model_profile &&
                `, chosen for ${record.model_profile.label}`}
            </dd>
          </div>
        )}
      </dl>
      {record.instructions && (
        <details className="creation-instructions">
          <summary>Saved task instructions</summary>
          <pre>{record.instructions}</pre>
        </details>
      )}
      <details className="creation-timeline">
        <summary>Publication activity</summary>
        <ol>
          {record.events.map((event, index) => (
            <li key={`${index}-${event.at}`}>
              {stages[event.name] || event.name}
              <time>{new Date(event.at).toLocaleString()}</time>
            </li>
          ))}
        </ol>
      </details>
      {!operationRunning && record.status !== 'deleted' && (
        <>
          {operatorKey}
          <div className="creation-actions">
            {['failed', 'interrupted'].includes(record.status) &&
              record.operation !== 'delete' &&
              record.error !== 'deletion_unconfirmed' && (
                <button
                  className="creation-secondary"
                  disabled={busy || !publishEnabled}
                  onClick={() => onOperate('resume')}
                >
                  Resume setup
                </button>
              )}
            <button
              className="creation-secondary"
              disabled={busy || !canManage}
              onClick={() => onOperate('delete')}
            >
              <Trash2 size={16} />
              Delete created agent
            </button>
          </div>
          <p className="creation-help">
            An operator can delete this created runtime for everyone. Export
            needed chats first. Existing catalog agents are not affected.
          </p>
        </>
      )}
      {record.status === 'deleted' && (
        <p className="creation-notice">
          <Check size={16} />
          Deletion was confirmed. The saved name and instructions were cleared.
        </p>
      )}
    </section>
  )
}
