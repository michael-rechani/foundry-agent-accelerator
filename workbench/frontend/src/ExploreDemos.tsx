import { useState } from 'react'
import {
  ArrowRight,
  Check,
  Clipboard,
  FileCheck2,
  FlaskConical,
  MessageSquare,
  ReceiptText,
} from 'lucide-react'
import {
  demoScenarios,
  agentForDemo,
  type DemoScenario,
} from './demo-scenarios'
import type { CreatedAgent } from './agent-creation-client'
import { isPreviewId } from './library-catalog'
import type { Agent, Config } from './workspace-config'
import './showcase.css'

const icons = [FileCheck2, ReceiptText, MessageSquare]

export function ExploreDemos({
  config,
  agents,
  created,
  previewFor,
  loadingAgents,
  agentError,
  busy,
  onLoad,
  onCreate,
  onChat,
}: {
  config: Config
  agents: Agent[]
  created: CreatedAgent[]
  previewFor: (templateId: string) => Agent | undefined
  loadingAgents: boolean
  agentError: string
  busy: boolean
  onLoad: (scenario: DemoScenario) => void
  onCreate: (label?: string) => void
  onChat: () => void
}) {
  const [selected, setSelected] = useState(demoScenarios[0])
  const [copyStatus, setCopyStatus] = useState('')
  const agent = agentForDemo(selected, agents, created, previewFor)
  const preview = !!agent && isPreviewId(agent.id)

  async function copyInput() {
    try {
      await navigator.clipboard.writeText(selected.input)
      setCopyStatus('Sample input copied. Nothing was sent.')
    } catch {
      setCopyStatus(
        'Clipboard unavailable. Open Sample input and select the text to copy it.',
      )
    }
  }

  return (
    <main className="demo-explorer" aria-label="Guided demos">
      <div className="demo-introduction">
        <h1>From paperwork to a clear next step.</h1>
        <p>
          Pick a practical question. Explore the evidence. Then try an agent and
          check what it actually returns.
        </p>
        <button className="inline-link" onClick={onChat}>
          Go straight to Chat <ArrowRight size={16} />
        </button>
      </div>
      <div className="demo-layout">
        <nav className="demo-choices" aria-label="Demo scenarios">
          {demoScenarios.map((scenario, index) => {
            const Icon = icons[index]
            return (
              <button
                key={scenario.id}
                aria-pressed={selected.id === scenario.id}
                onClick={() => {
                  setSelected(scenario)
                  setCopyStatus('')
                }}
              >
                <Icon size={23} aria-hidden="true" />
                <span>
                  <strong>{scenario.task}</strong>
                  <span>{scenario.title}</span>
                </span>
                <ArrowRight size={17} aria-hidden="true" />
              </button>
            )
          })}
        </nav>
        <article className="demo-story" aria-labelledby="demo-story-title">
          <header>
            <h2 id="demo-story-title">{selected.title}</h2>
            <p>{selected.description}</p>
          </header>
          <div className="demo-actions">
            {agent ? (
              <button
                className="demo-primary"
                disabled={busy}
                onClick={() => onLoad(selected)}
              >
                Load sample input <ArrowRight size={17} />
              </button>
            ) : config.agent_creation ? (
              <button
                className="demo-primary"
                disabled={busy}
                onClick={() => onCreate(selected.templateLabel)}
              >
                Choose {selected.templateLabel} <ArrowRight size={17} />
              </button>
            ) : (
              <p>
                No matching agent is configured. Ask the Lab operator to enable
                one.
              </p>
            )}
            <button className="demo-copy" onClick={() => void copyInput()}>
              <Clipboard size={16} /> Copy input
            </button>
          </div>
          <p className="demo-execution-note">
            {agent
              ? `Uses ${preview ? `the ${agent.label} library preview` : agent.label}. Loading only fills the composer; you choose when to Send.`
              : 'This story is available to read now. Using its template requires preparing and publishing an agent; nothing is created automatically.'}{' '}
            {config.mode === 'preview'
              ? 'Local preview makes no model calls and saves no records.'
              : preview
                ? 'Sending calls the model and can incur costs. Preview chats are not saved.'
                : 'Sending invokes Foundry and can incur costs. Saved records are shared.'}
          </p>
          <p className="demo-example-label">
            <FlaskConical size={16} aria-hidden="true" />
            Illustrative walkthrough, not a live model result
          </p>
          <div className="demo-evidence">
            <h3>What to look for</h3>
            <ol>
              {selected.findings.map((finding) => (
                <li key={finding.source}>
                  <Check size={17} aria-hidden="true" />
                  <div>
                    <strong>{finding.label}</strong>
                    <p>{finding.detail}</p>
                    <span className="demo-source">{finding.source}</span>
                  </div>
                </li>
              ))}
            </ol>
          </div>
          <div className="demo-decision">
            <h3>Your decision stays yours.</h3>
            <p>{selected.decision}</p>
          </div>
          <details className="demo-input" key={selected.id}>
            <summary>Sample input</summary>
            <pre>{selected.input}</pre>
          </details>
          {loadingAgents && (
            <p role="status">Checking which agents are available...</p>
          )}
          {agentError && (
            <p className="demo-error" role="alert">
              {agentError}
            </p>
          )}
          {copyStatus && <p role="status">{copyStatus}</p>}
        </article>
      </div>
      <div className="demo-next">
        <div>
          <h2>Want a version of your own?</h2>
          <p>
            Try any agent in the library with sample data first. Then make your
            own copy and change its instructions. Publishing a copy needs
            operator approval.
          </p>
        </div>
        {config.agent_creation && (
          <button className="inline-link" onClick={() => onCreate()}>
            Make your own agent <ArrowRight size={17} />
          </button>
        )}
      </div>
    </main>
  )
}

export function DemoRunGuide({
  scenario,
  presenting,
  busy,
  onFresh,
  onClose,
}: {
  scenario: DemoScenario
  presenting: boolean
  busy: boolean
  onFresh: () => void
  onClose: () => void
}) {
  return (
    <details className="demo-run-guide" open={presenting}>
      <summary>Demo guide: {scenario.task}</summary>
      <p>
        Expected findings, not a live result. Compare the actual reply with the
        sample source.
      </p>
      <ul>
        {scenario.findings.map((finding) => (
          <li key={finding.source}>{finding.detail}</li>
        ))}
      </ul>
      <p>{scenario.decision}</p>
      <div className="demo-guide-actions">
        <button className="inline-link" disabled={busy} onClick={onFresh}>
          Start fresh with this example
        </button>
        <button className="inline-link" onClick={onClose}>
          Close guide
        </button>
      </div>
      <p>
        Starting fresh only clears local messages after confirmation. It never
        deletes shared history or stops a deployed agent.
      </p>
    </details>
  )
}
