import type { ReactNode } from 'react'
import { ArrowRight, Download } from 'lucide-react'
import { specDefinition, specFileName, type AgentSpec } from './agent-spec'
import { saveFile } from './save-file'

// What the Agent designer's spec turns into. Both actions are the person's
// choice: the download only saves a file, and the template button only opens
// Create agent with the task filled in, where nothing is made until the last
// step is confirmed.
export function AgentSpecCard({
  spec,
  templateLabel,
  onCreateFromTemplate,
  build,
  tests,
}: {
  spec: AgentSpec
  templateLabel?: string
  onCreateFromTemplate?: () => void
  // Where the spec can be built into a real agent without leaving the chat.
  build?: ReactNode
  // Where the draft can be tried first, before anything is published.
  tests?: ReactNode
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
      {tests}
      {build}
      {!spec.closest_template && (
        <p className="agent-spec-note">
          No built-in template matches this idea, so the Lab can&apos;t create
          it here. Download the draft and configure it in your Foundry project.
        </p>
      )}
      <p className="agent-spec-note">
        {spec.tools_needed.length ? (
          <>
            Draft only: this file uses a model placeholder and does not
            configure the listed lookups or document sources. Set them up in
            Foundry, then test the agent before relying on it.
          </>
        ) : (
          <>
            Draft only: this file uses a model placeholder and configures no
            tools. Choose a model deployment in Foundry, then test the agent
            before relying on it.
          </>
        )}
      </p>
    </section>
  )
}
