import { FoundryLink } from './FoundryLink'
import { foundryAgentUrl } from './foundry-links'
import type { Agent, CreationCapability } from './workspace-config'

export function AgentGuide({
  agent,
  compact = false,
}: {
  agent: Agent
  compact?: boolean
}) {
  if (!agent.guidance)
    return (
      <p className="agent-guide-missing">
        This agent has no getting-started guide. Ask the person who set up the
        Lab what to give it and what to expect.
      </p>
    )
  const entries = [
    ['What to give it', agent.guidance.input],
    ['What it returns', agent.guidance.output],
    ...(!compact
      ? [
          ['How it works', agent.guidance.delegation],
          ["What it won't do", agent.guidance.limits],
        ]
      : []),
  ]
  return (
    <dl className={`agent-guide${compact ? ' agent-guide-compact' : ''}`}>
      {entries.map(([label, text]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{text}</dd>
        </div>
      ))}
    </dl>
  )
}

export function AgentRuntime({
  agent,
  foundryPortal,
}: {
  agent: Agent
  foundryPortal?: string | null
}) {
  const agentUrl = foundryAgentUrl(foundryPortal, agent.agent)
  return (
    <details className="catalog-runtime hood-only">
      <summary>Developer setup details</summary>
      <p className="category-label">{agent.category}</p>
      {agent.guidance && <p>{agent.guidance.delegation}</p>}
      <dl>
        <div>
          <dt>Catalog ID</dt>
          <dd>
            <code>{agent.id}</code>
          </dd>
        </div>
        <div>
          <dt>Runtime agent</dt>
          <dd>
            <code>{agent.agent}</code>
            {agentUrl && (
              <>
                {' '}
                <FoundryLink href={agentUrl}>Open in Foundry</FoundryLink>
              </>
            )}
          </dd>
        </div>
      </dl>
      <p>{Object.keys(agent.tools).length} tool bindings</p>
      <ul>
        {Object.entries(agent.tools).map(([tool, target]) => (
          <li key={tool}>
            <code>{tool}</code> to <code>{target}</code>
            {foundryPortal && (
              <>
                {' '}
                <FoundryLink href={foundryAgentUrl(foundryPortal, target)}>
                  Open in Foundry
                </FoundryLink>
              </>
            )}
          </li>
        ))}
      </ul>
      {agentUrl && <p>Open it in Foundry to see its traces and monitoring.</p>}
      <p>
        Configured targets, not execution proof. Check response execution
        details and receipts; stored receipts are not reverified.
      </p>
      <p className="agent-config-source">
        {agent.guidance?.configuration ||
          'Runtime configuration sources are not documented for this entry. Ask the Lab operator.'}
      </p>
      <p>
        The catalog maps endpoints and expected receipts. Editing it does not
        change a deployed agent&apos;s instructions or tools.
      </p>
    </details>
  )
}

export function ConfigurationGuide({
  creation,
  onCreate,
}: {
  creation?: CreationCapability
  onCreate?: () => void
}) {
  return (
    <details className="configuration-guide">
      <summary>Can I change an agent or make a new one?</summary>
      <p>
        Chatting never changes an agent. Examples only fill the message box, and
        editing your message doesn&apos;t change how the agent works.
      </p>
      <p>
        {creation
          ? "Create agent lets you describe a job, start from a template, and edit the new agent's name and instructions. Preparing a setup creates nothing. Publishing it to Foundry has to be turned on and confirmed by an operator."
          : "Agent creation isn't turned on in this Lab. You can use the existing agents and their examples."}
      </p>
      {creation && onCreate && (
        <button className="inline-link" onClick={onCreate}>
          Create an agent
        </button>
      )}
      <p>
        The people who run the Lab choose each agent&apos;s tools, data access
        and model. You can&apos;t edit a published agent from here.
      </p>
      <details className="configuration-sources">
        <summary>For developers: files and deployment settings</summary>
        <dl>
          <div>
            <dt>Labels, guidance and starters</dt>
            <dd>
              Developers edit <code>workbench\agents.json</code>, then rebuild
              and redeploy the Lab. These are UI settings, not runtime
              instructions.
            </dd>
          </div>
          <div>
            <dt>Instructions and tools</dt>
            <dd>
              Developers change the hosted-agent source or coordinator profile
              listed in each agent&apos;s runtime details, then publish and test
              a new agent version. The catalog&apos;s <code>agent</code>{' '}
              endpoint and <code>tools</code> receipt map must match that
              deployment; they do not register runtime tools.
            </dd>
          </div>
          <div>
            <dt>Visibility, default agent and Lab title</dt>
            <dd>
              Operators set <code>visible_agents</code>,{' '}
              <code>default_agent</code> and <code>workspace_title</code> in{' '}
              <code>workbench\infra</code> through a reviewed Lab rollout. Local
              equivalents are <code>WORKBENCH_VISIBLE_AGENTS</code>,{' '}
              <code>WORKBENCH_DEFAULT_AGENT</code> and{' '}
              <code>WORKBENCH_TITLE</code>; restart the local server to apply
              them.
            </dd>
          </div>
        </dl>
        <p>None of these developer settings can be edited from this UI.</p>
      </details>
    </details>
  )
}
