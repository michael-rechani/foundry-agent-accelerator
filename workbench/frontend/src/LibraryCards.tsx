import { ArrowRight, Check, UserCheck } from 'lucide-react'
import { agentIcons, fallbackAgentIcon } from './agent-icons'
import { demoScenarios } from './demo-scenarios'
import type { LibraryTemplate } from './library-catalog'
import { Badges } from './LibraryBadges'

// The tile is decoration; the agent's name beside it says everything.
function AgentIcon({ id }: { id: string }) {
  const Icon = agentIcons[id] ?? fallbackAgentIcon
  return (
    <span className="library-card-icon" aria-hidden="true">
      <Icon size={20} strokeWidth={1.8} />
    </span>
  )
}

export function LibraryCard({
  template,
  ready,
  onOpen,
}: {
  template: LibraryTemplate
  ready: boolean
  onOpen: () => void
}) {
  return (
    <button
      type="button"
      className="library-card"
      data-sector={template.sector.id}
      onClick={onOpen}
    >
      <span className="library-kicker">
        <span className="library-sector-dot" aria-hidden="true" />
        <span className="library-kicker-text">
          {template.sector.label} · {template.industry.label}
        </span>
      </span>
      <span className="library-card-head">
        <AgentIcon id={template.id} />
        <strong>{template.label}</strong>
      </span>
      <span className="library-summary">{template.summary}</span>
      <span className="library-decides">
        <UserCheck size={13} aria-hidden="true" />
        {template.human_decision}
      </span>
      <span className="library-badges">
        <Badges template={template} />
        {ready && (
          <span className="library-badge good">
            <Check size={12} aria-hidden="true" /> Made in this Lab
          </span>
        )}
      </span>
    </button>
  )
}

// Three agents with a ready-made example, taken from the guided demos so the
// two never drift apart. A card opens the agent's page, where "Try it with an
// example" sits.
export function StartHere({
  templates,
  onOpen,
}: {
  templates: LibraryTemplate[]
  onOpen: (templateId: string) => void
}) {
  const featured = demoScenarios.filter((scenario) =>
    templates.some((item) => item.id === scenario.templateId),
  )
  if (!featured.length) return null
  return (
    <section className="library-start" aria-labelledby="library-start">
      <div className="library-start-head">
        <h2 id="library-start">Start here</h2>
        <span>Open one to try it with an example.</span>
      </div>
      <ul className="library-start-list">
        {featured.map((scenario) => (
          <li key={scenario.id}>
            <button
              type="button"
              className="library-start-card"
              onClick={() => onOpen(scenario.templateId)}
            >
              <AgentIcon id={scenario.templateId} />
              <strong>{scenario.title}</strong>
              <span className="library-start-text">{scenario.description}</span>
              <span className="library-start-foot">
                <span>{scenario.templateLabel}</span>
                <ArrowRight size={16} aria-hidden="true" />
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
