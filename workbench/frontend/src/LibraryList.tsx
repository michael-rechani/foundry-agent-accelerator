import { ArrowRight, BadgeCheck, CircleDashed } from 'lucide-react'
import { agentIcons, fallbackAgentIcon } from './agent-icons'
import type { LibraryTemplate } from './library-catalog'
import { AvailabilityBadge } from './LibraryBadges'

const tones: Record<string, string> = {
  reviewed: 'good',
  'tested-live': 'good',
  sample: 'caution',
  simulated: 'info',
  'connected-required': 'caution',
}

function ReadinessBadge({ template }: { template: LibraryTemplate }) {
  const Icon = template.readiness.id === 'sample' ? CircleDashed : BadgeCheck
  return (
    <span
      className={`library-badge ${tones[template.readiness.id] || ''}`}
      title={template.readiness.description}
    >
      <Icon size={12} aria-hidden="true" />
      {template.readiness.label}
    </span>
  )
}

function AgentIcon({ id }: { id: string }) {
  const Icon = agentIcons[id] ?? fallbackAgentIcon
  return (
    <span className="library-card-icon library-list-icon" aria-hidden="true">
      <Icon size={18} strokeWidth={1.8} />
    </span>
  )
}

export function LibraryList({
  templates,
  onOpen,
  actionFor,
}: {
  templates: LibraryTemplate[]
  onOpen: (templateId: string) => void
  actionFor: (template: LibraryTemplate) => {
    disabled?: boolean
    label: string
    onClick: () => void
  }
}) {
  return (
    <div className="library-list-wrap">
      <table className="library-list-table">
        <caption className="visually-hidden">
          Agents matching the current filters
        </caption>
        <colgroup>
          <col style={{ width: '28%' }} />
          <col />
          <col style={{ width: '16%' }} />
          <col style={{ width: '15%' }} />
          <col style={{ width: '112px' }} />
        </colgroup>
        <thead>
          <tr>
            <th scope="col">Agent</th>
            <th scope="col">Job</th>
            <th scope="col">Sector</th>
            <th scope="col">Readiness</th>
            <th scope="col" className="library-list-action-heading">
              <span className="visually-hidden">Action</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {templates.map((template) => {
            const action = actionFor(template)
            return (
              <tr key={template.id}>
                <th scope="row">
                  <button
                    type="button"
                    className="library-list-open"
                    onClick={() => onOpen(template.id)}
                  >
                    <AgentIcon id={template.id} />
                    <strong>{template.label}</strong>
                  </button>
                </th>
                <td className="library-list-summary">
                  <span
                    className="library-list-summary-text"
                    title={template.summary}
                  >
                    {template.summary}
                  </span>
                </td>
                <td>
                  <span
                    className="library-kicker library-list-sector"
                    data-sector={template.sector.id}
                  >
                    <span className="library-sector-dot" aria-hidden="true" />
                    {template.sector.label}
                  </span>
                </td>
                <td>
                  <div className="library-badges library-list-badges">
                    <AvailabilityBadge template={template} />
                    <ReadinessBadge template={template} />
                  </div>
                </td>
                <td className="library-list-action-cell">
                  <button
                    type="button"
                    className="library-secondary library-list-action"
                    disabled={action.disabled}
                    onClick={action.onClick}
                  >
                    {action.label}
                    {action.label === 'Open' && <ArrowRight size={15} />}
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
