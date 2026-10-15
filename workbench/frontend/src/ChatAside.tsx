import { ArrowDownToLine, LoaderCircle, Plus, Save } from 'lucide-react'
import { AgentGuide, AgentRuntime } from './AgentGuide'
import type { Turn } from './conversation-types'
import { FoundryLink } from './FoundryLink'
import { foundryAgentUrl } from './foundry-links'
import {
  createFromPreviewNote,
  previewBlurb,
  publishedBlurb,
} from './library-helpers'
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
        <details className="aside-about" key={agent.id}>
          <summary>
            <h2 id="aside-about">About this agent</h2>
          </summary>
          <div className="aside-more-body">
            <span className={`aside-kind${isPreview ? ' preview' : ''}`}>
              {isPreview ? 'Library preview' : agent.category}
            </span>
            <p>{agent.description}</p>
            <AgentGuide agent={agent} />
            <p>{isPreview ? previewBlurb : publishedBlurb}</p>
            <AgentRuntime agent={agent} foundryPortal={portal} />
            <button type="button" className="inline-link" onClick={onCatalog}>
              Change agent
            </button>
          </div>
        </details>
      </section>

      <section className="aside-panel" aria-labelledby="aside-conversation">
        <h2 id="aside-conversation">This conversation</h2>
        <dl className="aside-rows">
          {config && (
            <div>
              <dt>Reply limit</dt>
              <dd>
                {turns.length} of {config.max_history_turns + 1} replies used
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
                title={createFromPreviewNote}
                onClick={onCreateThis}
              >
                <Plus size={16} />
                Create this agent
              </button>
              <p>Nothing is created until you confirm on the last step.</p>
            </>
          ) : (
            <button
              type="button"
              className="aside-button"
              title={
                saveNote ||
                'Save to shared history. Everyone who uses this Lab can open it.'
              }
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
            title="Downloads a file to your computer and shares nothing."
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
