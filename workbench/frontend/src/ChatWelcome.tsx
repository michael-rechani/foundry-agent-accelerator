import { ArrowRight, Construction, FlaskConical } from 'lucide-react'
import { AgentGuide } from './AgentGuide'
import type { Agent, Config } from './workspace-config'

const snippet = (text: string) => {
  const flat = text.replace(/\s+/g, ' ').trim()
  return flat.length > 110 ? `${flat.slice(0, 107).trimEnd()}…` : flat
}

export function ChatWelcome({
  agent,
  config,
  isPreview,
  inProgress = false,
  onPrompt,
}: {
  agent?: Agent
  config: Config | null
  isPreview: boolean
  inProgress?: boolean
  onPrompt: (text: string) => void
}) {
  return (
    <div className="chat-welcome">
      {agent && (
        <div className="welcome-tags">
          <span className={`welcome-kind${isPreview ? ' preview' : ''}`}>
            {isPreview ? 'Library preview' : agent.category}
          </span>
          {inProgress && (
            <span
              className="progress-pill"
              title="Passes offline tests; not yet validated against a live model"
            >
              <Construction size={12} aria-hidden="true" /> In progress
            </span>
          )}
        </div>
      )}
      <h1>{agent?.label || 'Connecting to your workspace'}</h1>
      {agent && <p>{agent.description}</p>}
      {agent && <AgentGuide agent={agent} compact />}
      {isPreview && (
        <p className="welcome-preview-note">
          This preview runs the library definition on the Lab&apos;s model with
          fictional lookups only. Nothing is published, and preview chats are
          not saved.
        </p>
      )}
      {!!agent?.prompts.length && (
        <>
          <h2 className="welcome-examples-title">Start with an example</h2>
          <div className="prompt-options">
            {agent.prompts.map((prompt) => (
              <button
                key={prompt.label}
                disabled={!config}
                onClick={() => onPrompt(prompt.text)}
              >
                <FlaskConical size={16} aria-hidden="true" />
                <span>
                  <strong>{prompt.label}</strong>
                  <small>{snippet(prompt.text)}</small>
                </span>
                <ArrowRight size={15} aria-hidden="true" />
              </button>
            ))}
          </div>
        </>
      )}
      {agent && (
        <p className="welcome-hint">
          {config?.mode === 'preview'
            ? 'Local preview: examples fill the message box. No model calls or saved records.'
            : 'An example fills the message box so you can edit it. Nothing is sent until you press Send.'}
        </p>
      )}
    </div>
  )
}
