import { ArrowDownToLine, LoaderCircle, Plus, Save } from 'lucide-react'
import { AgentGuide, AgentRuntime } from './AgentGuide'
import type { Turn } from './conversation-types'
import { FoundryLink } from './FoundryLink'
import { foundryAgentUrl } from './foundry-links'
import { formatTokens, totalUsage } from './token-usage'
import type { Agent, Config } from './workspace-config'
import './chat-aside.css'

const seconds = (ms: number) => `${(ms / 1000).toFixed(1)} s`

// A side column for wide screens. It holds what the top bar and the "About
// this agent" pop-up used to hold, so the conversation keeps the middle.
export function ChatAside({
  agent,
  config,
  isPreview,
  turns,
  characters,
  saving,
  saveDisabled,
  saveNote,
  exportDisabled,
  onCatalog,
  onSave,
  onExport,
  onCreateThis,
}: {
  agent: Agent
  config: Config | null
  isPreview: boolean
  turns: Turn[]
  characters: number
  saving: boolean
  saveDisabled: boolean
  saveNote?: string
  exportDisabled: boolean
  onCatalog: () => void
  onSave: () => void
  onExport: () => void
  onCreateThis?: () => void
}) {
  const tokens = totalUsage(turns.map((turn) => turn.result.usage ?? null))
  const last = turns.length ? turns[turns.length - 1].result : null
  const portal = isPreview ? null : config?.foundry_portal
  const agentUrl = foundryAgentUrl(portal, agent.agent)
  return (
    <aside className="chat-aside" aria-label="Agent details">
      <section className="aside-panel" aria-labelledby="aside-about">
        <h2 id="aside-about">About this agent</h2>
        <span className={`aside-kind${isPreview ? ' preview' : ''}`}>
          {isPreview ? 'Library preview' : agent.category}
        </span>
        <p>{agent.description}</p>
        <AgentGuide agent={agent} compact />
        <details className="aside-more">
          <summary>More about this agent</summary>
          <div className="aside-more-body">
            {agent.guidance && (
              <dl className="agent-guide">
                <div>
                  <dt>How it works</dt>
                  <dd>{agent.guidance.delegation}</dd>
                </div>
                <div>
                  <dt>What it won&apos;t do</dt>
                  <dd>{agent.guidance.limits}</dd>
                </div>
              </dl>
            )}
            <p>
              {isPreview
                ? 'Library preview: the Lab runs this definition on its model with sample lookups only. Nothing is published, and preview chats are not saved.'
                : 'This agent already has a published setup. Your message gives it a task; it does not change its tools or permanent instructions.'}
            </p>
            <AgentRuntime agent={agent} foundryPortal={portal} />
            <button type="button" className="inline-link" onClick={onCatalog}>
              Choosing or changing an agent
            </button>
          </div>
        </details>
      </section>

      <section className="aside-panel" aria-labelledby="aside-conversation">
        <h2 id="aside-conversation">This conversation</h2>
        <dl className="aside-rows">
          {config && (
            <div>
              <dt>Replies</dt>
              <dd>
                {turns.length} / {config.max_history_turns + 1}
              </dd>
            </div>
          )}
          {last && (
            <div>
              <dt>Last reply took</dt>
              <dd>{seconds(last.elapsed_ms)}</dd>
            </div>
          )}
          {!!turns.length && (
            <div className="hood-only">
              <dt>Tokens</dt>
              <dd>
                {tokens.measured
                  ? `${formatTokens(tokens.input)} in · ${formatTokens(tokens.output)} out`
                  : 'Not reported'}
              </dd>
            </div>
          )}
          {!!tokens.measured && !!tokens.missing && (
            <div className="hood-only">
              <dt>Not reported</dt>
              <dd>
                {tokens.missing} {tokens.missing === 1 ? 'reply' : 'replies'}
              </dd>
            </div>
          )}
          {config && (
            <div className="hood-only">
              <dt>Characters</dt>
              <dd>
                {characters.toLocaleString()} /{' '}
                {config.max_characters.toLocaleString()}
              </dd>
            </div>
          )}
        </dl>
      </section>

      <section className="aside-panel" aria-labelledby="aside-next">
        <h2 id="aside-next">Next steps</h2>
        <div className="aside-actions">
          {onCreateThis ? (
            <>
              <button
                type="button"
                className="aside-button primary"
                title="Preview chats can't be saved. Create this agent to save chats and take it to Foundry. Nothing is created until the last step."
                onClick={onCreateThis}
              >
                <Plus size={16} />
                Create this agent
              </button>
              <p>Nothing is created until the last step.</p>
            </>
          ) : (
            <button
              type="button"
              className="aside-button"
              title={saveNote || 'Save to shared history'}
              aria-describedby={
                config?.mode === 'private' ? 'chat-privacy' : undefined
              }
              disabled={saveDisabled}
              onClick={onSave}
            >
              {saving ? (
                <LoaderCircle size={16} className="spin" />
              ) : (
                <Save size={16} />
              )}
              Save to shared history
            </button>
          )}
          <button
            type="button"
            className="aside-button"
            title="Export conversation"
            disabled={exportDisabled}
            onClick={onExport}
          >
            <ArrowDownToLine size={16} />
            Export conversation
          </button>
          {agentUrl && (
            <FoundryLink href={agentUrl} className="aside-link hood-only">
              See traces in Foundry
            </FoundryLink>
          )}
        </div>
      </section>
    </aside>
  )
}
