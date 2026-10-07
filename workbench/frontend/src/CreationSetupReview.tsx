import type { ReactNode } from 'react'
import { LoaderCircle, Plus } from 'lucide-react'
import type {
  AgentDraft,
  AgentTemplate,
  CreatePayload,
} from './agent-creation-client'

export function CreationSetupReview({
  draft,
  template,
  templateModel,
  name,
  instructions,
  consent,
  pending,
  busy,
  publishEnabled,
  validSetup,
  operatorKey,
  onChangeTask,
  onName,
  onInstructions,
  onConsent,
  onPublish,
  onCheck,
}: {
  draft: AgentDraft
  template?: AgentTemplate
  templateModel?: string | null
  name: string
  instructions: string
  consent: boolean
  pending: CreatePayload | null
  busy: boolean
  publishEnabled: boolean
  validSetup: boolean
  operatorKey: ReactNode
  onChangeTask: () => void
  onName: (value: string) => void
  onInstructions: (value: string) => void
  onConsent: (value: boolean) => void
  onPublish: () => void
  onCheck: () => void
}) {
  return (
    <section className="creation-setup" aria-label="Review agent setup">
      <div className="creation-setup-heading">
        <h2>Review your agent setup</h2>
        <button
          className="inline-link"
          disabled={busy || !!pending}
          onClick={onChangeTask}
        >
          Change task or template
        </button>
      </div>
      <p>
        Prepared from <strong>{template?.label}</strong> and your description.
        No agent has been created yet.
      </p>
      {template && (
        <dl className="creation-explanation">
          <div>
            <dt>What to give it</dt>
            <dd>{template.input}</dd>
          </div>
          <div>
            <dt>What it returns</dt>
            <dd>{template.output}</dd>
          </div>
          <div>
            <dt>How it works</dt>
            <dd>{template.delegation}</dd>
          </div>
          <div>
            <dt>What it won&apos;t do</dt>
            <dd>{template.limits}</dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd>
              {templateModel ? (
                <code>{templateModel}</code>
              ) : (
                'Set by the Lab operator'
              )}
              {', chosen for '}
              <strong>{template.model_profile.label}</strong>
              {'. '}
              {template.model_profile.reason}
            </dd>
          </div>
        </dl>
      )}
      <label>
        Agent name
        <input
          value={name}
          disabled={busy || !!pending}
          onChange={(event) => onName(event.target.value)}
        />
      </label>
      <label>
        Task instructions
        <textarea
          rows={7}
          value={instructions}
          disabled={busy || !!pending}
          onChange={(event) => onInstructions(event.target.value)}
        />
      </label>
      <small>
        {[...instructions].length}/6000 instruction characters. Name: up to 80
        characters.
      </small>
      <p className="creation-help">
        The template fixes the tools, runtime rules and model. A chat prompt
        can't change them.
      </p>
      {template?.tools.length ? (
        <ul className="creation-tool-list">
          {template.tools.map((tool) => (
            <li key={tool.name}>
              <code>{tool.name}</code> - {tool.description}
              {tool.simulated ? ' (sample data)' : ''}
            </li>
          ))}
        </ul>
      ) : (
        <p className="creation-help">No tools or external integrations.</p>
      )}
      <details className="creation-instructions">
        <summary>Sample input</summary>
        <pre>{draft.sample_input}</pre>
      </details>
      {operatorKey}
      <label className="creation-consent">
        <input
          type="checkbox"
          checked={consent}
          disabled={busy || !!pending}
          onChange={(event) => onConsent(event.target.checked)}
        />
        <span>
          I confirm creating a shared Foundry agent can incur hosting, build and
          model charges. Closing this page does not stop the runtime.
        </span>
      </label>
      {pending && (
        <p className="creation-notice">
          This request may already be saved. Check its status or retry the same
          request; do not create another copy. Request ID:{' '}
          <code>{pending.idempotency_key}</code>
        </p>
      )}
      <div className="creation-actions">
        <button
          className="creation-primary"
          onClick={onPublish}
          disabled={busy || !publishEnabled || !validSetup || !consent}
        >
          {busy ? (
            <LoaderCircle size={16} className="spin" />
          ) : (
            <Plus size={16} />
          )}
          {pending ? 'Retry same creation request' : 'Create in Foundry'}
        </button>
        {pending && (
          <button
            className="creation-secondary"
            disabled={busy}
            onClick={onCheck}
          >
            Check creation status
          </button>
        )}
      </div>
    </section>
  )
}
