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
    ['What you give it', agent.guidance.input],
    ['What you get', agent.guidance.output],
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

export function AgentRuntime({ agent }: { agent: Agent }) {
  return (
    <details className="catalog-runtime">
      <summary>Developer setup details</summary>
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
          </dd>
        </div>
      </dl>
      <p>{Object.keys(agent.tools).length} tool bindings</p>
      <ul>
        {Object.entries(agent.tools).map(([tool, target]) => (
          <li key={tool}>
            <code>{tool}</code> to <code>{target}</code>
          </li>
        ))}
      </ul>
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
      <summary>Can I create or change an agent here?</summary>
      <p>
        A starter is just an example task and message, not a new agent. Editing
        a Chat message does not change the agent&apos;s permanent setup.
      </p>
      <p>
        {creation
          ? "Create agent lets you describe a job, choose a prepared template and edit the new agent's name and task instructions. An operator must enable and explicitly confirm real publication in Foundry. Preparing a setup alone creates no resource."
          : 'This server does not advertise agent creation. You can use the existing agents and their example tasks.'}
      </p>
      {creation && onCreate && (
        <button className="inline-link" onClick={onCreate}>
          Prepare an agent setup
        </button>
      )}
      <p>
        Tools, source access, runtime code and the model remain
        developer/operator settings. Existing deployed agents are not edited in
        place by this UI.
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
