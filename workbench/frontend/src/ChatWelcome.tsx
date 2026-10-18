import { useState, type ComponentProps } from 'react'
import {
  ArrowRight,
  Check,
  ChevronsUpDown,
  CircleDashed,
  MessageSquare,
  Sparkles,
} from 'lucide-react'
import { AgentGuide } from './AgentGuide'
import { LabGuide } from './LabGuide'
import { agentKind, inProgressNote, previewBlurb } from './library-helpers'
import { useSimpleChat } from './simple-chat'
import type { Agent, Config } from './workspace-config'

export type LabGuideProps = Omit<
  ComponentProps<typeof LabGuide>,
  'title' | 'initialTopic'
>

// What is in the message box: nothing, an example the app put there, or the
// person's own words.
export type DraftMode = 'empty' | 'example' | 'typed'

// The first sentence of a starter says what the agent will do with it.
const outcome = (text: string) => {
  const flat = text.replace(/\s+/g, ' ').trim()
  return flat.match(/^.*?[.!?](?=\s|$)/)?.[0] ?? flat
}

// One short line. Once the person types, the message box speaks for itself.
function welcomeHint(preview: boolean, draftMode: DraftMode) {
  if (preview)
    return draftMode === 'empty'
      ? 'Local preview: examples fill the message box. No model calls or saved records.'
      : draftMode === 'example'
        ? 'Local preview: your example is in the message box. Pick another to replace it. No model calls or saved records.'
        : 'Local preview. No model calls or saved records.'
  return draftMode === 'example'
    ? 'Your example is in the message box below. Edit it or press Send, or pick another to replace it.'
    : ''
}

export function ChatWelcome({
  agent,
  config,
  isPreview,
  inProgress = false,
  draftMode,
  lab,
  switchDisabled = false,
  onAsk,
  onSwitch,
  onPrompt,
}: {
  agent?: Agent
  config: Config | null
  isPreview: boolean
  inProgress?: boolean
  draftMode: DraftMode
  // What the "What can I create?" card shows, written from the Lab's own lists.
  lab: LabGuideProps
  switchDisabled?: boolean
  onAsk: () => void
  onSwitch: () => void
  onPrompt: (text: string) => void
}) {
  const [simple, setSimple] = useSimpleChat()
  const hint = !agent
    ? ''
    : simple
      ? config?.mode === 'preview'
        ? 'Local preview. No model calls or saved records.'
        : ''
      : welcomeHint(config?.mode === 'preview', draftMode)
  const [chosen, setChosen] = useState<string>()
  const [creating, setCreating] = useState(false)
  const showModes = !simple && !!config && draftMode !== 'typed'
  return (
    <div className="chat-welcome">
      {agent && !simple && (
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
      {simple ? (
        <>
          <h1>What would you like to do?</h1>
          <p>Try a ready-made agent, or talk through one you want to build.</p>
        </>
      ) : (
        <>
          <h1>{agent?.label || 'Connecting to your workspace'}</h1>
          {agent && <p>{agent.description}</p>}
        </>
      )}
      {agent && !simple && inProgress && (
        <p className="welcome-preview-note">{inProgressNote}</p>
      )}
      {agent && !simple && <AgentGuide agent={agent} compact />}
      {isPreview && !simple && (
        <p className="welcome-preview-note">{previewBlurb}</p>
      )}
      {simple && !!config && draftMode !== 'typed' && (
        <div className="welcome-modes welcome-simple-modes">
          <button type="button" disabled={switchDisabled} onClick={onSwitch}>
            <ChevronsUpDown size={16} aria-hidden="true" />
            <span>
              <strong>Try a new agent</strong>
              <small>Pick a ready agent and chat with it.</small>
            </span>
          </button>
          <button type="button" onClick={onAsk}>
            <MessageSquare size={16} aria-hidden="true" />
            <span>
              <strong>Chat about an agent I'm building</strong>
              <small>Think it through in your own words.</small>
            </span>
          </button>
        </div>
      )}
      {agent && (
        <button
          type="button"
          className="welcome-simple-toggle"
          aria-pressed={simple}
          onClick={() => setSimple(!simple)}
        >
          <MessageSquare size={14} aria-hidden="true" />
          {simple ? 'Show agent guide and examples' : 'Simple view'}
        </button>
      )}
      {showModes && (
        <>
          <h2 className="welcome-examples-title">
            How would you like to start?
          </h2>
          <div className="welcome-modes">
            <button type="button" onClick={onAsk}>
              <MessageSquare size={16} aria-hidden="true" />
              <span>
                <strong>Ask anything</strong>
                <small>Type your own message.</small>
              </span>
            </button>
            <button
              type="button"
              aria-expanded={creating}
              aria-controls="welcome-create"
              onClick={() => setCreating((value) => !value)}
            >
              <Sparkles size={16} aria-hidden="true" />
              <span>
                <strong>What can I create?</strong>
                <small>See the agents and how they are built.</small>
              </span>
            </button>
            <button type="button" disabled={switchDisabled} onClick={onSwitch}>
              <ChevronsUpDown size={16} aria-hidden="true" />
              <span>
                <strong>Switch agent</strong>
                <small>Choose a different prebuilt agent.</small>
              </span>
            </button>
          </div>
          {creating && (
            <div className="welcome-create" id="welcome-create">
              <LabGuide
                {...lab}
                title="What can I create?"
                initialTopic="agents"
              />
            </div>
          )}
        </>
      )}
      {!simple && draftMode !== 'typed' && !!agent?.prompts.length && (
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
      {hint && <p className="welcome-hint">{hint}</p>}
    </div>
  )
}
