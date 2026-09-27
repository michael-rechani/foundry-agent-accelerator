import { ArrowRight, FlaskConical } from 'lucide-react'
import { AgentGuide } from './AgentGuide'
import type { Agent, Config } from './workspace-config'

export function ChatWelcome({
  agent,
  config,
  onPrompt,
  onReviews,
}: {
  agent?: Agent
  config: Config | null
  onPrompt: (text: string) => void
  onReviews: () => void
}) {
  return (
    <div className="chat-welcome">
      <h1>Use {agent?.label || 'an existing agent'}</h1>
      <p>{agent?.description || 'Connecting to your workspace'}</p>
      {agent && <AgentGuide agent={agent} compact />}
      <p>
        You are using an existing agent, not creating one. Choose an example
        task below or write your own message, then Send.
      </p>
      <div className="prompt-options">
        {agent?.prompts.map((prompt) => (
          <button
            key={prompt.label}
            disabled={!config}
            onClick={() => onPrompt(prompt.text)}
          >
            <FlaskConical size={16} />
            <span>{prompt.label}</span>
            <ArrowRight size={15} />
          </button>
        ))}
      </div>
      {config?.reviews_enabled && (
        <p className="chat-review-link">
          Want a saved check of each item on your checklist? Use{' '}
          <button className="inline-link" onClick={onReviews}>
            Document reviews
          </button>
          . It starts separately; your Chat messages are not copied over.
        </p>
      )}
      {config?.mode === 'preview' && (
        <p className="preview-explanation">
          Local preview: try writing a message with made-up details. No model
          calls or saved records.
        </p>
      )}
    </div>
  )
}
