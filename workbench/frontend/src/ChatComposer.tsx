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
  hasConversation,
  characters,
  requestBytes,
  contextUsage,
  limitReasons,
  saved,
  dirty,
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
  hasConversation: boolean
  characters: number
  requestBytes: number
  contextUsage: number
  limitReasons: string[]
  saved: boolean
  dirty: boolean
  onDraft: (value: string) => void
  onSubmit: () => void
  onStop: () => void
  onContinue: () => void
}) {
  const exceedsLimit = limitReasons.length > 0
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
            config && hasConversation ? 'context-budget' : undefined
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
            <FlaskConical size={12} aria-hidden="true" />
            {config?.mode === 'private'
              ? 'Use made-up examples; you make decisions'
              : 'No model calls or saving'}
          </span>
          <div>
            {turnCount > 0 && (
              <button
                type="button"
                className="chat-icon"
                title="Continue in new chat"
                aria-label="Continue in new chat"
                disabled={busy || historyBusy}
                onClick={onContinue}
              >
                <GitBranch size={17} />
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
      {hasConversation && (
        <div className="composer-details">
          {config && (
            <details
              className={`context-budget ${contextUsage >= 0.9 ? 'near-limit' : ''}`}
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
            {saved
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
