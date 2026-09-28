import type { RefObject } from 'react'
import { ArrowUp, FlaskConical, GitBranch, Square } from 'lucide-react'
import type { Agent, Config } from './workspace-config'

export function ChatComposer({
  editor,
  agent,
  config,
  draft,
  busy,
  historyBusy,
  turnCount,
  characters,
  requestBytes,
  contextUsage,
  limitReasons,
  saved,
  dirty,
  isPreview,
  onDraft,
  onSubmit,
  onStop,
  onContinue,
}: {
  editor: RefObject<HTMLTextAreaElement | null>
  agent?: Agent
  config: Config | null
  draft: string
  busy: boolean
  historyBusy: boolean
  turnCount: number
  characters: number
  requestBytes: number
  contextUsage: number
  limitReasons: string[]
  saved: boolean
  dirty: boolean
  isPreview: boolean
  onDraft: (value: string) => void
  onSubmit: () => void
  onStop: () => void
  onContinue: () => void
}) {
  const exceedsLimit = limitReasons.length > 0
  // Limits and save state only matter once there is something to lose.
  const showDetails = turnCount > 0 || contextUsage >= 0.5
  return (
    <div className="composer-area">
      <form
        className={`composer ${exceedsLimit ? 'over-limit' : ''}`}
        onSubmit={(event) => {
          event.preventDefault()
          onSubmit()
        }}
      >
        <textarea
          ref={editor}
          aria-label="Message"
          placeholder={`Message ${agent?.label || 'your agent'}...`}
          value={draft}
          aria-describedby={
            [
              config?.mode === 'private' && 'chat-privacy',
              config && showDetails && 'context-budget',
            ]
              .filter(Boolean)
              .join(' ') || undefined
          }
          disabled={busy}
          rows={3}
          onChange={(event) => onDraft(event.target.value)}
          onKeyDown={(event) => {
            if (
              event.key === 'Enter' &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing
            ) {
              event.preventDefault()
              onSubmit()
            }
          }}
        />
        <div className="composer-toolbar">
          <span>
            {config?.mode !== 'private' && (
              <>
                <FlaskConical size={12} aria-hidden="true" />
                No model calls or saving
              </>
            )}
          </span>
          <div>
            {turnCount > 0 && (
              <button
                type="button"
                className="composer-continue"
                title="Start a new chat that carries this reply forward"
                aria-label="Continue in new chat"
                disabled={busy || historyBusy}
                onClick={onContinue}
              >
                <GitBranch size={15} aria-hidden="true" />
                <span>Continue in new chat</span>
              </button>
            )}
            {busy ? (
              <button
                key="stop"
                type="button"
                className="send-button stop"
                aria-label="Stop waiting"
                title="Stop waiting"
                onClick={(event) => {
                  event.preventDefault()
                  onStop()
                }}
              >
                <Square size={16} />
              </button>
            ) : (
              <button
                key="send"
                type="submit"
                className="send-button"
                disabled={
                  !agent || !draft.trim() || exceedsLimit || historyBusy
                }
                aria-label="Send message"
                title="Send message"
              >
                <ArrowUp size={20} />
              </button>
            )}
          </div>
        </div>
      </form>
      {config?.mode === 'private' && (
        <p className="composer-privacy" id="chat-privacy">
          Use sample data only, never personal or confidential information. Each
          message calls the model and may incur cost.
          {isPreview
            ? ' Preview chats are not saved.'
            : config.history_enabled &&
              ` Saving shares completed messages with everyone in this Lab for ${config.retention_days} days after the last update.`}
        </p>
      )}
      {showDetails && (
        <div className="composer-details">
          {config && (
            <details
              className={`context-budget ${contextUsage >= 0.9 ? 'near-limit' : 'hood-only'}`}
              id="context-budget"
            >
              <summary>
                Conversation limits{' '}
                <span>{Math.round(contextUsage * 100)}%</span>
              </summary>
              <dl>
                <div>
                  <dt>Characters</dt>
                  <dd>
                    {characters.toLocaleString()} /{' '}
                    {config.max_characters.toLocaleString()}
                  </dd>
                </div>
                <div>
                  <dt>Request bytes</dt>
                  <dd>
                    {requestBytes.toLocaleString()} /{' '}
                    {config.max_request_bytes.toLocaleString()}
                  </dd>
                </div>
                <div>
                  <dt>Replies</dt>
                  <dd>
                    {turnCount} / {config.max_history_turns + 1}
                  </dd>
                </div>
              </dl>
            </details>
          )}
          <span className="save-state">
            {isPreview
              ? 'Preview · not saved'
              : saved
                ? dirty
                  ? 'Unsaved changes'
                  : draft
                    ? 'Draft not saved'
                    : 'Saved / shared'
                : 'Not saved'}
          </span>
        </div>
      )}
      {exceedsLimit ? (
        <p className="composer-warning" role="alert">
          {limitReasons.join(' ')} Shorten your message or start a new chat.
        </p>
      ) : contextUsage >= 0.9 ? (
        <p className="composer-warning">Approaching the conversation limit.</p>
      ) : null}
    </div>
  )
}
