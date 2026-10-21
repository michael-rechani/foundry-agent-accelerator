import { ArrowRight, Download } from 'lucide-react'
import { specDefinition, specFileName, type AgentSpec } from './agent-spec'
import { saveFile } from './save-file'

// What the Agent designer's spec turns into. Both actions are the person's
// choice: the download only saves a file, and the template button only opens
// Create agent, where nothing is made until the last step is confirmed.
export function AgentSpecCard({
  spec,
  templateLabel,
  onCreateFromTemplate,
}: {
  spec: AgentSpec
  templateLabel?: string
  onCreateFromTemplate?: () => void
}) {
  const details: [string, string][] = [
    ['Takes in', spec.inputs],
    ['Returns', spec.outputs],
    ['A person decides', spec.human_decision],
    ['Needs lookups', spec.tools_needed.join(', ')],
  ]
  return (
    <section className="agent-spec" aria-label="Agent spec">
      <h4>{spec.name}</h4>
      <p>{spec.summary}</p>
      <dl>
        {details
          .filter(([, value]) => value)
          .map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
      </dl>
      <div className="agent-spec-actions">
        <button
          type="button"
          className="library-secondary"
          onClick={() =>
            saveFile(
              specFileName(spec),
              JSON.stringify(specDefinition(spec), null, 2) + '\n',
              'application/json',
            )
          }
        >
          <Download size={16} aria-hidden="true" /> Download agent spec
        </button>
        {templateLabel && onCreateFromTemplate && (
          <button
            type="button"
            className="library-secondary"
            onClick={onCreateFromTemplate}
          >
            Start from {templateLabel} in Create agent{' '}
            <ArrowRight size={16} aria-hidden="true" />
          </button>
        )}
      </div>
      <p className="agent-spec-note">
        The file is a Foundry prompt agent definition. Add your own model
        deployment. Nothing is created until you act.
      </p>
    </section>
  )
}
