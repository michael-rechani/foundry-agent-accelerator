import { useEffect, useRef, useState } from 'react'
import { ArrowRight, Check, MessageCircleQuestion } from 'lucide-react'
import {
  addOnGroupLabels,
  addOns,
  type AddOn,
  type AddOnGroup,
} from './add-on-catalog'
import type { Agent } from './workspace-config'

type Topic = 'agents' | 'build'

const topics: { id: Topic; question: string }[] = [
  { id: 'agents', question: 'Which agent should I use or build?' },
  { id: 'build', question: 'How is an agent built, and what can I add?' },
]

const groups: AddOnGroup[] = ['abilities', 'support']

const addOnStatus = (item: AddOn) =>
  item.pilot ? 'Sample pilot' : 'Not available yet'

function AgentsAnswer({
  agents,
  current,
  onChooseAgent,
  onCreateAgent,
}: {
  agents: Agent[]
  current?: Agent
  onChooseAgent: (id: string) => void
  onCreateAgent?: () => void
}) {
  return (
    <>
      <p>
        {agents.length
          ? 'These agents are ready in this Lab. Pick the one that matches the job, then start from one of its examples.'
          : 'No agents are ready in this Lab yet.'}
      </p>
      {!!agents.length && (
        <ul className="lab-guide-agents">
          {agents.map((item) => (
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
      )}
      <p>
        {onCreateAgent
          ? 'None of them fit? You can describe the job and start a new agent from a template.'
          : "Agent creation isn't turned on in this Lab, so only these agents are available."}
      </p>
      {onCreateAgent && (
        <button type="button" className="inline-link" onClick={onCreateAgent}>
          Create an agent
        </button>
      )}
    </>
  )
}

function BuildAnswer({
  current,
  onAddOns,
}: {
  current?: Agent
  onAddOns: () => void
}) {
  return (
    <>
      <p>
        An agent is a set of instructions, a model that does the thinking, and
        the tools it is allowed to use. Add-ons are optional extras on top, such
        as search over your documents or a place to keep files.
      </p>
      {current?.guidance && (
        <p>
          <strong>{current.label}:</strong> {current.guidance.delegation}
        </p>
      )}
      <p>
        Chatting never changes an agent. The people who run the Lab choose each
        agent&apos;s instructions, tools and model.
      </p>
      {groups.map((group) => (
        <div key={group} className="lab-guide-group">
          <h4>{addOnGroupLabels[group]}</h4>
          <ul>
            {addOns
              .filter((item) => item.group === group)
              .map((item) => (
                <li key={item.id}>
                  <span>
                    <strong>{item.name}</strong>
                    <small>{item.summary}</small>
                  </span>
                  <span className="lab-guide-status">{addOnStatus(item)}</span>
                </li>
              ))}
          </ul>
        </div>
      ))}
      <p>
        This list is a preview. Nothing here turns anything on or costs money.
      </p>
      <button type="button" className="inline-link" onClick={onAddOns}>
        See what each add-on would cost and need
      </button>
    </>
  )
}

// Two questions people ask first. The answers are written from the Lab's own
// agent list and add-on catalogue, so asking sends nothing and makes no model
// call. A free-form guide is a separate, later step.
export function LabGuide({
  agents,
  current,
  onChooseAgent,
  onAddOns,
  onCreateAgent,
  title = 'Ask the Lab',
}: {
  agents: Agent[]
  current?: Agent
  onChooseAgent: (id: string) => void
  onAddOns: () => void
  onCreateAgent?: () => void
  title?: string
}) {
  const [topic, setTopic] = useState<Topic | null>(null)
  const answer = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    if (topic) answer.current?.focus()
  }, [topic])
  const asked = topics.find((item) => item.id === topic)
  return (
    <section className="lab-guide" aria-labelledby="lab-guide-title">
      <h2 id="lab-guide-title">
        <MessageCircleQuestion size={14} aria-hidden="true" /> {title}
      </h2>
      <div className="lab-guide-questions">
        {topics.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-expanded={topic === item.id}
            aria-controls="lab-guide-answer"
            onClick={() => setTopic(topic === item.id ? null : item.id)}
          >
            <span>{item.question}</span>
            <ArrowRight size={15} aria-hidden="true" />
          </button>
        ))}
      </div>
      {asked && (
        <div className="lab-guide-exchange" id="lab-guide-answer">
          <p className="lab-guide-bubble">{asked.question}</p>
          <div className="lab-guide-answer">
            <h3 ref={answer} tabIndex={-1}>
              {asked.id === 'agents'
                ? 'Agents you can use'
                : 'How an agent is built'}
            </h3>
            {asked.id === 'agents' ? (
              <AgentsAnswer
                agents={agents}
                current={current}
                onChooseAgent={onChooseAgent}
                onCreateAgent={onCreateAgent}
              />
            ) : (
              <BuildAnswer current={current} onAddOns={onAddOns} />
            )}
            <p className="lab-guide-note">
              Written by the Lab from its own lists. Nothing is sent or saved.
            </p>
          </div>
        </div>
      )}
    </section>
  )
}
