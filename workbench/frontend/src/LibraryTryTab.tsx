import { ArrowRight, Copy, MessageSquare } from 'lucide-react'
import type { LibraryTemplate } from './library-catalog'
import { creationNote, type ReadyAgent } from './library-helpers'
import type { Agent, CreationCapability } from './workspace-config'

export function LibraryTryTab({
  template,
  capability,
  ready,
  preview,
  busy,
  onCreate,
  onTest,
  onNotice,
}: {
  template: LibraryTemplate
  capability?: CreationCapability
  ready?: ReadyAgent
  preview?: Agent
  busy: boolean
  onCreate: () => void
  onTest: (agent: Agent, input: string) => void
  onNotice: (text: string) => void
}) {
  const runnable = template.tool_mode.id !== 'connected-required'

  async function copySample() {
    try {
      await navigator.clipboard.writeText(template.sample_input)
      onNotice('Example input copied.')
    } catch {
      onNotice('Clipboard unavailable. Select and copy the example manually.')
    }
  }

  return (
    <div className="library-columns">
      <section className="library-panel">
        <h2>Example to try</h2>
        <pre className="library-sample">{template.sample_input}</pre>
        <div className="library-actions">
          {!runnable ? (
            <p className="library-muted">
              This agent needs a connection to your own system and cannot run in
              the Lab.
            </p>
          ) : preview ? (
            <button
              type="button"
              className="library-primary"
              disabled={busy}
              onClick={() => onTest(preview, template.sample_input)}
            >
              <MessageSquare size={16} /> Try it in Chat
            </button>
          ) : null}
          {runnable && ready ? (
            <button
              type="button"
              className={preview ? 'library-secondary' : 'library-primary'}
              disabled={busy}
              onClick={() => onTest(ready.agent, template.sample_input)}
            >
              Open your created agent <ArrowRight size={16} />
            </button>
          ) : runnable && !preview ? (
            <button
              type="button"
              className="library-primary"
              disabled={!capability || busy}
              onClick={onCreate}
            >
              Create this agent to test it <ArrowRight size={16} />
            </button>
          ) : null}
          <button
            type="button"
            className="library-secondary"
            onClick={() => void copySample()}
          >
            <Copy size={15} /> Copy example
          </button>
        </div>
        <p className="library-muted">
          {preview
            ? 'Opens Chat with this example ready to send. Nothing happens until you press Send, which calls the model and has a small cost. Preview chats aren\u2019t saved.'
            : ready
              ? `Uses ${ready.agent.label}. Opens Chat with this example ready to send. Nothing happens until you press Send, which calls the model and has a small cost.`
              : creationNote(capability)}
        </p>
        {preview && (
          <p className="library-muted hood-only">
            A preview calls the model directly rather than running as a hosted
            agent, so test the created agent before handing it to a customer.
          </p>
        )}
      </section>
      <section className="library-panel">
        <h2>What to look for in the answer</h2>
        <ul className="library-checks">
          <li>{template.expected_behavior}</li>
          <li>It stays within its limits. {template.limits}</li>
          <li>It leaves the decision to a person.</li>
        </ul>
        <p className="library-muted">
          {preview
            ? 'Use sample data only. Preview chats are not saved; create the agent to save or share conversations.'
            : 'Use sample data only. Chat responses are not saved unless you choose Save to shared history.'}
        </p>
      </section>
    </div>
  )
}
