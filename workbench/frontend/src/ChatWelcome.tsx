import { useState } from 'react'
import { ArrowRight, Check, CircleDashed } from 'lucide-react'
import { AgentGuide } from './AgentGuide'
import { agentKind, inProgressNote, previewBlurb } from './library-helpers'
import { LabGuide } from './LabGuide'
import type { Agent, Config } from './workspace-config'

// What is in the message box: nothing, an example the app put there, or the
// person's own words.
export type DraftMode = 'empty' | 'example' | 'typed'

// The first sentence of a starter says what the agent will do with it.
const outcome = (text: string) => {
  const flat = text.replace(/\s+/g, ' ').trim()
  return flat.match(/^.*?[.!?](?=\s|$)/)?.[0] ?? flat
}

function welcomeHint(preview: boolean, draftMode: DraftMode) {
  if (preview)
    return draftMode === 'empty'
      ? 'Local preview: examples fill the message box. No model calls or saved records.'
      : draftMode === 'example'
        ? 'Local preview: your example is in the message box. Pick another to replace it. No model calls or saved records.'
        : 'Local preview. No model calls or saved records.'
  return draftMode === 'empty'
    ? 'Pick an example to fill the message box, or type your own. Nothing is sent until you press Send.'
    : draftMode === 'example'
      ? 'Your example is in the message box below. Edit it, or pick another to replace it. Nothing is sent until you press Send.'
      : 'Nothing is sent until you press Send.'
}

export function ChatWelcome({
  agent,
  config,
  isPreview,
  inProgress = false,
  draftMode,
  onPrompt,
  onCreateAgent,
  agents,
  onChooseAgent,
  onAddOns,
}: {
  agent?: Agent
  config: Config | null
  isPreview: boolean
  inProgress?: boolean
  draftMode: DraftMode
  onPrompt: (text: string) => void
  onCreateAgent?: () => void
  agents?: Agent[]
  onChooseAgent?: (id: string) => void
  onAddOns?: () => void
}) {
  const [chosen, setChosen] = useState<string>()
  return (
    <div className="chat-welcome">
      {agent && (
        <div className="welcome-tags">
          <span className={`welcome-kind${isPreview ? ' preview' : ''}`}>
            {agentKind(agent)}
          </span>
          {inProgress && (
            <span className="progress-pill" title={inProgressNote}>
              <CircleDashed size={12} aria-hidden="true" /> Not yet reviewed
            </span>
          )}
        </div>
      )}
      <h1>{agent?.label || 'Connecting to your workspace'}</h1>
      {agent && <p>{agent.description}</p>}
      {agent && inProgress && (
        <p className="welcome-preview-note">{inProgressNote}</p>
      )}
      {agent && <AgentGuide agent={agent} compact />}
      {isPreview && <p className="welcome-preview-note">{previewBlurb}</p>}
      {draftMode !== 'typed' && !!agent?.prompts.length && (
        <>
          <h2 className="welcome-examples-title">Start with an example</h2>
          <div className="prompt-options">
            {agent.prompts.map((prompt, index) => {
              const selected =
                draftMode === 'example' && chosen === prompt.label
              return (
                <button
                  key={prompt.label}
                  className={selected ? 'selected' : undefined}
                  disabled={!config}
                  aria-label={prompt.label}
                  aria-pressed={selected}
                  aria-describedby={`welcome-prompt-${index}`}
                  onClick={() => {
                    setChosen(prompt.label)
                    onPrompt(prompt.text)
                  }}
                >
                  <span>
                    <strong>{prompt.label}</strong>
                    <small id={`welcome-prompt-${index}`}>
                      {outcome(prompt.text)}
                    </small>
                  </span>
                  {selected ? (
                    <Check size={15} aria-hidden="true" />
                  ) : (
                    <ArrowRight size={15} aria-hidden="true" />
                  )}
                </button>
              )
            })}
          </div>
        </>
      )}
      {agent && (
        <p className="welcome-hint">
          {welcomeHint(config?.mode === 'preview', draftMode)}
        </p>
      )}
      {agent && onCreateAgent && (
        <p className="welcome-hint welcome-create">
          Need something else?{' '}
          <button type="button" className="inline-link" onClick={onCreateAgent}>
            Create an agent
          </button>{' '}
          from a template.
        </p>
      )}
      {agent && agents && onChooseAgent && onAddOns && (
        <LabGuide
          key={agent.id}
          agents={agents}
          current={agent}
          onChooseAgent={onChooseAgent}
          onAddOns={onAddOns}
          onCreateAgent={onCreateAgent}
        />
      )}
    </div>
  )
}
