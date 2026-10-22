import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, Search } from 'lucide-react'
import { findMatches } from './guide-finder'
import type { LibraryTemplate } from './library-catalog'
import type { Agent } from './workspace-config'
import './job-finder.css'

// Plain-word examples taken from the agents that are ready, so each one finds
// something real.
function suggestionsFor(agents: Agent[]) {
  const labels = agents.flatMap((agent) =>
    agent.prompts
      .map((prompt) => prompt.label.replace(/\s*\(preview\)$/i, '').trim())
      .filter((label) => label && !/^help me get started$/i.test(label)),
  )
  return [...new Set(labels)].slice(0, 4)
}

// Finds an agent or template for a job the person describes. It matches words
// against the Lab's own lists, so it calls no model and sends nothing. A
// model-backed guide is a separate, approved step (#261).
export function JobFinder({
  agents,
  templates,
  current,
  onChooseAgent,
  onUseTemplate,
  onBrowse,
  onCreateAgent,
}: {
  agents: Agent[]
  templates: LibraryTemplate[]
  current?: Agent
  onChooseAgent: (id: string) => void
  onUseTemplate?: (id: string) => void
  onBrowse: () => void
  onCreateAgent?: () => void
}) {
  const [text, setText] = useState('')
  const [asked, setAsked] = useState<string | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const suggestions = useMemo(() => suggestionsFor(agents), [agents])
  const found = useMemo(
    () => (asked ? findMatches(asked, agents, templates) : null),
    [asked, agents, templates],
  )
  useEffect(() => {
    if (asked) heading.current?.focus()
  }, [asked])

  function ask(value: string) {
    const trimmed = value.trim()
    if (trimmed) setAsked(trimmed)
  }

  const nothing = !!found && !found.agents.length && !found.templates.length
  return (
    <section className="job-finder" aria-labelledby="job-finder-title">
      <h2 id="job-finder-title">Describe the job</h2>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          ask(text)
        }}
      >
        <label htmlFor="job-finder-input">What are you trying to do?</label>
        <div className="job-finder-row">
          <input
            id="job-finder-input"
            type="text"
            value={text}
            maxLength={300}
            autoComplete="off"
            placeholder="For example: check a document against a checklist"
            onChange={(event) => setText(event.target.value)}
          />
          <button type="submit" disabled={!text.trim()}>
            <Search size={14} aria-hidden="true" /> Find an agent
          </button>
        </div>
      </form>
      {!!suggestions.length && (
        <div className="job-finder-suggestions">
          <span>Try:</span>
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => {
                setText(suggestion)
                ask(suggestion)
              }}
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}
      <p className="job-finder-note">
        This looks for your words in the Lab&apos;s agents and templates. It
        does not use an AI model, and nothing is sent or saved.
      </p>
      {found && (
        <div className="job-finder-results" id="job-finder-results">
          <h3 ref={heading} tabIndex={-1}>
            {nothing ? 'No match found' : 'Best matches'} for &ldquo;{asked}
            &rdquo;
          </h3>
          {!!found.agents.length && (
            <>
              <h4>Ready to use</h4>
              <ul>
                {found.agents.map((item) => (
                  <li key={item.id}>
                    <span>
                      <strong>{item.label}</strong>
                      <small>{item.description}</small>
                    </span>
                    {item.id === current?.id ? (
                      <span className="lab-guide-current">
                        <Check size={13} aria-hidden="true" /> In use now
                      </span>
                    ) : (
                      <button
                        type="button"
                        aria-label={`Use ${item.label}`}
                        onClick={() => onChooseAgent(item.id)}
                      >
                        Use this agent
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
          {!!found.templates.length && (
            <>
              <h4>Templates to build from</h4>
              <ul>
                {found.templates.map((item) => (
                  <li key={item.id}>
                    <span>
                      <strong>{item.label}</strong>
                      <small>{item.summary}</small>
                    </span>
                    <button
                      type="button"
                      aria-label={
                        onUseTemplate
                          ? `Start from the ${item.label} template`
                          : `Browse the library for ${item.label}`
                      }
                      onClick={() =>
                        onUseTemplate ? onUseTemplate(item.id) : onBrowse()
                      }
                    >
                      {onUseTemplate ? 'Start from this' : 'See in library'}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
          {nothing && (
            <p>
              Nothing in this Lab matches those words. Try different words, or
              {onCreateAgent ? ' start a new agent.' : ' browse the library.'}
            </p>
          )}
          {nothing && (
            <button
              type="button"
              className="inline-link"
              onClick={onCreateAgent ?? onBrowse}
            >
              {onCreateAgent ? 'Create an agent' : 'Browse the agent library'}
            </button>
          )}
        </div>
      )}
    </section>
  )
}
