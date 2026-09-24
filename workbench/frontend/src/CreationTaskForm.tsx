import { useRef } from 'react'
import { ArrowRight, LoaderCircle } from 'lucide-react'
import { groupTemplates, type AgentTemplate } from './agent-creation-client'

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
  return (
    <>
      <div
        className="creation-template-groups"
        aria-label="Prepared agent templates"
      >
        {groupTemplates(templates).map(([category, items]) => (
          <section
            key={category}
            className="creation-template-group"
            aria-label={category}
          >
            <h2>{category}</h2>
            <div className="creation-templates">
              {items.map((item) => (
                <button
                  key={item.id}
                  className="creation-template"
                  aria-pressed={templateId === item.id}
                  disabled={busy}
                  onClick={() => {
                    onPick(item)
                    goalField.current?.focus()
                  }}
                >
                  <strong>{item.label}</strong>
                  <span>{item.description}</span>
                  <small>
                    {item.tools.length
                      ? 'Simulated read-only lookups'
                      : 'Supplied text; no tools'}
                  </small>
                </button>
              ))}
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
        <label>
          What should the agent help with?
          <textarea
            ref={goalField}
            rows={3}
            value={goal}
            disabled={busy}
            onChange={(event) => onGoal(event.target.value)}
            placeholder="For example: Create an agent that summarizes fictional policy notices and identifies questions for staff."
          />
        </label>
        <small>
          {[...goal].length}/1200 characters; at least 10. Use made-up details,
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
