import { ArrowRight, FileCheck2, GitBranch, Search } from 'lucide-react'
import { AgentGuide, AgentRuntime, ConfigurationGuide } from './AgentGuide'
import type { Agent, CreationCapability } from './workspace-config'

export function AgentCatalog({
  agents,
  selected,
  query,
  loaded,
  creation,
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
  return (
    <main className="secondary-view">
      <div className="section-heading">
        <h1>Choose an agent</h1>
        <p>
          Choose an enabled existing agent or a ready agent created in this
          shared Lab. Each has a saved job and fixed tools. Selecting one does
          not create a new agent.
        </p>
      </div>
      <ConfigurationGuide creation={creation} onCreate={onCreate} />
      <details className="catalog-status">
        <summary>Sample scope and status</summary>
        <p>
          Casework assistance and application completeness are available.
          Automated tests use simulated responses, so check live answers
          yourself. Requirements and proposal review is in preview and reuses
          application review.
        </p>
        <p>
          These samples target Microsoft Foundry. They aren&apos;t an official
          Microsoft product.
        </p>
      </details>
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
              <span className="category-label">{item.category}</span>
            </div>
            <h2>{item.label}</h2>
            <p>{item.description}</p>
            <AgentGuide agent={item} />
            <AgentRuntime agent={item} />
            <button
              className="catalog-select"
              disabled={disabled}
              onClick={() => onChoose(item.id)}
            >
              {item.id === selected ? 'Return to chat' : 'Start chat'}
              <ArrowRight size={17} />
            </button>
          </article>
        ))}
      </div>
      {loaded && !matches.length && (
        <p className="no-data">No matching agents</p>
      )}
    </main>
  )
}
