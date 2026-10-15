import { useRef, useState } from 'react'
import {
  ArrowRight,
  Brain,
  Check,
  Cpu,
  LoaderCircle,
  Search,
  Wrench,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import { agentIcons, fallbackAgentIcon } from './agent-icons'
import { groupTemplates, type AgentTemplate } from './agent-creation-client'

const profileIcons: Record<string, LucideIcon> = {
  reasoning: Brain,
  extraction: Zap,
  tool_calling: Wrench,
}

export function CreationTaskForm({
  templates,
  templateId,
  goal,
  busy,
  onPick,
  onTemplateId,
  onGoal,
  onPrepare,
}: {
  templates: AgentTemplate[]
  templateId: string
  goal: string
  busy: boolean
  onPick: (template: AgentTemplate) => void
  onTemplateId: (id: string) => void
  onGoal: (goal: string) => void
  onPrepare: () => void
}) {
  const goalField = useRef<HTMLTextAreaElement>(null)
  const [search, setSearch] = useState('')
  const needle = search.trim().toLowerCase()
  const groups = groupTemplates(templates)
    .map(
      ([category, items]) =>
        [
          category,
          items.filter(
            (item) =>
              !needle ||
              `${item.label} ${item.description}`
                .toLowerCase()
                .includes(needle),
          ),
        ] as const,
    )
    .filter(([, items]) => items.length)
  const picked = templates.find((item) => item.id === templateId)
  return (
    <>
      <label className="creation-search">
        <Search size={16} aria-hidden="true" />
        <span className="visually-hidden">Search templates</span>
        <input
          type="search"
          value={search}
          placeholder="Search templates, for example invoice or ticket"
          onChange={(event) => setSearch(event.target.value)}
        />
      </label>
      {needle && !groups.length && (
        <p className="creation-help" role="status">
          No templates match &ldquo;{search.trim()}&rdquo;. Clear the search to
          see all {templates.length}.
        </p>
      )}
      <div
        className="creation-template-groups"
        aria-label="Prepared agent templates"
      >
        {groups.map(([category, items]) => (
          <section
            key={category}
            className="creation-template-group"
            aria-label={category}
          >
            <h2>{category}</h2>
            <div className="creation-templates">
              {items.map((item) => {
                const Icon = agentIcons[item.id] ?? fallbackAgentIcon
                const ProfileIcon = profileIcons[item.model_profile.id] ?? Cpu
                const selected = templateId === item.id
                return (
                  <button
                    key={item.id}
                    className="creation-template"
                    aria-pressed={selected}
                    data-profile={item.model_profile.id}
                    disabled={busy}
                    onClick={() => {
                      onPick(item)
                      goalField.current?.focus()
                      goalField.current?.scrollIntoView({ block: 'center' })
                    }}
                  >
                    <span className="creation-template-icon" aria-hidden="true">
                      <Icon size={20} strokeWidth={1.8} />
                    </span>
                    {selected && (
                      <span
                        className="creation-template-check"
                        aria-hidden="true"
                      >
                        <Check size={14} strokeWidth={2.6} />
                      </span>
                    )}
                    <strong>{item.label}</strong>
                    <span className="creation-template-description">
                      {item.description}
                    </span>
                    <span className="creation-template-meta">
                      <span className="creation-chip creation-chip-model">
                        <ProfileIcon size={12} aria-hidden="true" />
                        <span className="visually-hidden">Model: </span>
                        {item.model_profile.label}
                      </span>
                      <small className="creation-chip creation-chip-tools">
                        {item.tools.length
                          ? 'Sample read-only lookups'
                          : 'Supplied text; no tools'}
                      </small>
                    </span>
                  </button>
                )
              })}
            </div>
          </section>
        ))}
      </div>
      <form
        className="creation-form"
        onSubmit={(event) => {
          event.preventDefault()
          onPrepare()
        }}
      >
        {picked && (
          <p className="creation-picked" role="status">
            <Check size={14} aria-hidden="true" /> Selected: {picked.label}.
            Describe the job below, then choose Prepare setup.
          </p>
        )}
        <label>
          What should the agent help with?
          <textarea
            ref={goalField}
            rows={3}
            value={goal}
            disabled={busy}
            onChange={(event) => onGoal(event.target.value)}
            placeholder="For example: Create an agent that summarizes policy notices and identifies questions for staff."
          />
        </label>
        <small>
          {[...goal].length}/1200 characters; at least 10. Use sample details,
          not customer or patient information.
        </small>
        <label>
          Prepared template
          <select
            value={templateId}
            disabled={busy}
            onChange={(event) => onTemplateId(event.target.value)}
          >
            <option value="">Match my description, or ask me to choose</option>
            {groupTemplates(templates).map(([category, items]) => (
              <optgroup key={category} label={category}>
                {items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <p className="creation-help">
          Setup uses a prepared template and your task description. It does not
          call a model, generate runtime code or save an agent.
        </p>
        <button
          className="creation-primary"
          disabled={
            busy ||
            !templates.length ||
            [...goal.trim()].length < 10 ||
            [...goal].length > 1200
          }
        >
          {busy ? (
            <LoaderCircle size={16} className="spin" />
          ) : (
            <ArrowRight size={16} />
          )}
          Prepare setup
        </button>
      </form>
    </>
  )
}
