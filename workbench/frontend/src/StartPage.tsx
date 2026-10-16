import { ArrowRight, MessageSquare, Wrench } from 'lucide-react'
import { LabGuide } from './LabGuide'
import type { Agent } from './workspace-config'
import './library.css'
import './start-page.css'

// The first page. People ask the Lab a question before they meet an agent, then
// choose to try a ready agent or to build their own.
export function StartPage({
  agents,
  onChooseAgent,
  onTryAgent,
  onBuild,
  onAddOns,
  onCreateAgent,
}: {
  agents: Agent[]
  onChooseAgent: (id: string) => void
  onTryAgent: () => void
  onBuild: () => void
  onAddOns: () => void
  onCreateAgent?: () => void
}) {
  return (
    <main className="secondary-view library-view start-page" aria-label="Start">
      <header className="library-hero">
        <p className="library-eyebrow">Start here</p>
        <h1>Welcome to the Lab</h1>
        <p>
          Not sure where to begin? Ask the Lab first. When you are ready, try
          one of the agents that are already working, or build your own.
        </p>
      </header>
      <LabGuide
        agents={agents}
        onChooseAgent={onChooseAgent}
        onAddOns={onAddOns}
        onCreateAgent={onCreateAgent}
      />
      <section className="start-next" aria-labelledby="start-next-title">
        <h2 id="start-next-title">Then take a next step</h2>
        <div className="start-next-cards">
          <button type="button" onClick={onTryAgent}>
            <MessageSquare size={18} aria-hidden="true" />
            <span>
              <strong>Try an agent</strong>
              <small>Pick a ready agent and chat with it.</small>
            </span>
            <ArrowRight size={15} aria-hidden="true" />
          </button>
          <button type="button" onClick={onBuild}>
            <Wrench size={18} aria-hidden="true" />
            <span>
              <strong>Build your own</strong>
              <small>
                {onCreateAgent
                  ? 'Start a new agent from a template.'
                  : 'Browse the agent library for a starting point.'}
              </small>
            </span>
            <ArrowRight size={15} aria-hidden="true" />
          </button>
        </div>
      </section>
    </main>
  )
}
