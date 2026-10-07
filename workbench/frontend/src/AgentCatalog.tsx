import { ArrowRight, FileCheck2, GitBranch, Search } from 'lucide-react'
import { AgentGuide, AgentRuntime, ConfigurationGuide } from './AgentGuide'
import { agentKind } from './library-helpers'
import type { Agent, CreationCapability } from './workspace-config'

const sendNote = 'Nothing is sent until you press Send.'

// The count is the same one the "Ready to chat" tab shows.
function readySummary(count: number | null) {
  if (count === null) return sendNote
  if (!count) return 'No agents are ready to chat yet.'
  return `${count} ${count === 1 ? 'agent is' : 'agents are'} ready to chat. ${sendNote}`
}

export function AgentCatalog({
  agents,
  selected,
  query,
  loaded,
  creation,
  previewsOn,
  foundryPortal,
  disabled,
  onQuery,
  onCreate,
  onChoose,
}: {
  agents: Agent[]
  selected: string
  query: string
  loaded: boolean
  creation?: CreationCapability
  previewsOn: boolean
  foundryPortal?: string | null
  disabled: boolean
  onQuery: (query: string) => void
  onCreate: () => void
  onChoose: (id: string) => void
}) {
  const matches = agents.filter((item) =>
    `${item.label} ${item.description} ${item.category}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  )
  const tail = !loaded
    ? ''
    : previewsOn
      ? 'Library agents can be tried as previews from Browse.'
      : creation?.enabled
        ? 'To try another library agent, open Browse and make your own copy.'
        : ''
  return (
    <main className="secondary-view">
      <div className="section-heading">
        <h1>Choose an agent</h1>
        <p>
          {[readySummary(loaded ? agents.length : null), tail]
            .filter(Boolean)
            .join(' ')}
        </p>
      </div>
      <ConfigurationGuide creation={creation} onCreate={onCreate} />
      <details className="catalog-status hood-only">
        <summary>Sample scope and status</summary>
        <p>
          Checklist reviews and case notes summaries are available. Automated
          tests don&apos;t call the live model, so check live answers yourself.
          Comparing proposals with requirements is in preview and reuses the
          checklist reviewer.
        </p>
        <p>
          These samples target Microsoft Foundry. They aren&apos;t an official
          Microsoft product.
        </p>
      </details>
      <div className="catalog-paths hood-only">
        <p>
          <strong>Use an agent</strong>Pick one below to open Chat. A listing
          does not prove the agent is reachable or that its answers are right.
        </p>
        <p>
          <strong>Create your own</strong>If agent creation is turned on, start
          in Create agent. Publishing needs operator approval and can incur
          costs.
        </p>
        <p>
          <strong>Repository drafts</strong>Agent drafts in the repository are
          documentation only. They are not deployed and do not connect to
          business systems.
        </p>
      </div>
      <label className="catalog-search">
        <Search size={17} />
        <input
          aria-label="Search agents"
          placeholder="Search agents"
          value={query}
          onChange={(event) => onQuery(event.target.value)}
        />
      </label>
      <div className="agent-grid">
        {matches.map((item) => (
          <article className="catalog-agent" key={item.id}>
            <div className="catalog-agent-top">
              <span className="catalog-avatar">
                {Object.keys(item.tools).length > 0 ? (
                  <GitBranch size={25} />
                ) : (
                  <FileCheck2 size={25} />
                )}
              </span>
              <span className="catalog-kind">{agentKind(item)}</span>
            </div>
            <h2>{item.label}</h2>
            <p>{item.description}</p>
            <AgentGuide agent={item} compact />
            {item.guidance && (
              <p className="catalog-human-decision">
                <strong className="catalog-guide-label">
                  What it won&apos;t do
                </strong>
                {item.guidance.limits}
              </p>
            )}
            <AgentRuntime agent={item} foundryPortal={foundryPortal} />
            <button
              className="catalog-select"
              disabled={disabled}
              onClick={() => onChoose(item.id)}
            >
              {item.id === selected ? 'Return to chat' : 'Chat with this agent'}
              <ArrowRight size={17} />
            </button>
          </article>
        ))}
      </div>
      {loaded && !!agents.length && !matches.length && (
        <p className="no-data">No matching agents</p>
      )}
    </main>
  )
}
