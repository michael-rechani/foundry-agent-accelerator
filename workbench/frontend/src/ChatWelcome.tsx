import { useEffect, useRef } from 'react'
import { ArrowRight, CircleDashed, FlaskConical } from 'lucide-react'
import { AgentGuide } from './AgentGuide'
import { agentKind, inProgressNote, previewBlurb } from './library-helpers'
import { LabGuide } from './LabGuide'
import type { Agent, Config } from './workspace-config'

// What is in the message box: nothing, an example the app put there, or the
// person's own words.
export type DraftMode = 'empty' | 'example' | 'typed'

const snippet = (text: string) => {
  const flat = text.replace(/\s+/g, ' ').trim()
  return flat.length > 110 ? `${flat.slice(0, 107).trimEnd()}…` : flat
}

function welcomeHint(preview: boolean, draftMode: DraftMode) {
  if (preview)
    return draftMode === 'empty'
      ? 'Local preview: examples fill the message box. No model calls or saved records.'
      : draftMode === 'example'
        ? 'Local preview: your example is in the message box. No model calls or saved records.'
        : 'Local preview. No model calls or saved records.'
  return draftMode === 'empty'
    ? 'Pick an example to fill the message box, or type your own. Nothing is sent until you press Send.'
    : draftMode === 'example'
      ? 'Your example is in the message box below. Edit it if you like. Nothing is sent until you press Send.'
      : 'Nothing is sent until you press Send.'
}

export function ChatWelcome({
  agent,
  config,
  isPreview,
  inProgress = false,
  draftMode,
  onPrompt,
  onClearExample,
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
  onClearExample?: () => void
  onCreateAgent?: () => void
  agents?: Agent[]
  onChooseAgent?: (id: string) => void
  onAddOns?: () => void
}) {
  const canSwapExample =
    draftMode === 'example' &&
    (agent?.prompts.length ?? 0) > 1 &&
    !!onClearExample
  const options = useRef<HTMLDivElement>(null)
  const refocusOptions = useRef(false)
  // The link that cleared the example is gone, so hand focus to the examples.
  useEffect(() => {
    if (draftMode !== 'empty' || !refocusOptions.current) return
    refocusOptions.current = false
    options.current?.querySelector('button')?.focus()
  }, [draftMode])
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
      {agent && <AgentGuide agent={agent} compact />}
      {isPreview && <p className="welcome-preview-note">{previewBlurb}</p>}
      {draftMode === 'empty' && !!agent?.prompts.length && (
        <>
          <h2 className="welcome-examples-title">Start with an example</h2>
          <div className="prompt-options" ref={options}>
            {agent.prompts.map((prompt, index) => (
              <button
                key={prompt.label}
                disabled={!config}
                aria-label={prompt.label}
                aria-describedby={`welcome-prompt-${index}`}
                onClick={() => onPrompt(prompt.text)}
              >
                <FlaskConical size={16} aria-hidden="true" />
                <span>
                  <strong>{prompt.label}</strong>
                  <small id={`welcome-prompt-${index}`}>
                    {snippet(prompt.text)}
                  </small>
                </span>
                <ArrowRight size={15} aria-hidden="true" />
              </button>
            ))}
          </div>
        </>
      )}
      {agent && (
        <p className="welcome-hint">
          {welcomeHint(config?.mode === 'preview', draftMode)}
          {canSwapExample && (
            <>
              {' '}
              <button
                type="button"
                className="inline-link"
                onClick={() => {
                  refocusOptions.current = true
                  onClearExample?.()
                }}
              >
                Choose a different example
              </button>
            </>
          )}
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
