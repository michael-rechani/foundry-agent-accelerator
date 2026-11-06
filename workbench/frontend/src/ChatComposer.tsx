import type { RefObject } from 'react'
import {
  ArrowUp,
  Copy,
  FlaskConical,
  GitBranch,
  Mic,
  Square,
} from 'lucide-react'
import { saveStateText } from './chat-helpers'
import { DESIGNER_ID } from './agent-designer'
import { useVoiceInput } from './use-voice-input'
import { DICTATION_DISCLOSURE } from './voice-input'
import type { Agent, Config } from './workspace-config'

export function ChatComposer({
  editor,
  clean = false,
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
  onCopyPrompt,
  onStop,
  onContinue,
}: {
  editor: RefObject<HTMLTextAreaElement | null>
  // The first screen is not about one agent yet.
  clean?: boolean
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
  onCopyPrompt: () => void
  onStop: () => void
  onContinue: () => void
}) {
  const exceedsLimit = limitReasons.length > 0
  const voice = useVoiceInput(draft, onDraft)
  // Local preview never calls a model, so Send would only ever fail.
  const localPreview = config?.mode === 'preview'
  // Limits and save state only matter once there is something to lose.
  const showDetails = turnCount > 0 || contextUsage >= 0.5
  const plain = agent?.id === DESIGNER_ID
  const unsavedPreview = isPreview && !plain
  const inToolbar = config?.mode === 'private'
  const hint = !localPreview && (
    <span className="composer-hint" id="composer-hint">
      {busy
        ? 'You can keep typing. Send turns on when the reply arrives.'
        : 'Enter sends. Shift+Enter adds a new line.'}
    </span>
  )
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
          placeholder={
            busy
              ? 'Waiting for a reply. You can write your next message now.'
              : plain && turnCount > 0
                ? 'Reply...'
                : clean
                  ? 'Describe the agent you want to build, or the job you need done...'
                  : `Message ${agent?.label || 'your agent'}...`
          }
          value={draft}
          aria-describedby={
            [
              !localPreview && 'composer-hint',
              config?.mode === 'private' && 'chat-privacy',
              config && showDetails && 'context-budget',
            ]
              .filter(Boolean)
              .join(' ') || undefined
          }
          rows={3}
          onChange={(event) => onDraft(event.target.value)}
          onKeyDown={(event) => {
            if (
              !localPreview &&
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
            {turnCount > 0 && !plain && (
              <button
                type="button"
                className="composer-continue"
                title="Carries the latest answer into a draft in a new chat, so you can build on it. Nothing is sent."
                aria-label="Continue in a new chat"
                disabled={busy || historyBusy}
                onClick={onContinue}
              >
                <GitBranch size={15} aria-hidden="true" />
                <span>Continue in a new chat</span>
              </button>
            )}
            {inToolbar && hint}
            {config?.mode !== 'private' && (
              <>
                <FlaskConical size={12} aria-hidden="true" />
                {localPreview
                  ? 'Local preview makes no model calls. Copy the prompt to use it in a connected Lab.'
                  : 'No model calls or saving'}
              </>
            )}
          </span>
          <div>
            {voice.supported && (
              <button
                type="button"
                className="mic-button"
                aria-label="Dictate message"
                aria-pressed={voice.listening}
                title="Dictate with your microphone. Your browser's speech service may send audio to its provider."
                onClick={voice.toggle}
              >
                <Mic size={18} aria-hidden="true" />
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
            ) : localPreview ? (
              <button
                key="copy"
                type="button"
                className="send-button copy-prompt"
                disabled={!draft.trim()}
                aria-label="Copy prompt"
                title="Copy prompt"
                onClick={onCopyPrompt}
              >
                <Copy size={18} aria-hidden="true" />
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
      {!inToolbar && hint}
      {voice.supported && (
        <p className="composer-voice-status" aria-live="polite">
          {voice.status}
        </p>
      )}
      {config?.mode === 'private' && (
        <div className="composer-privacy">
          <p id="chat-privacy">
            Sample data only. AI use may cost money.
            {unsavedPreview
              ? " Preview chats aren't saved."
              : config.history_enabled
                ? ' Saved chats are shared.'
                : ''}
          </p>
          <details>
            <summary>Privacy &amp; sharing</summary>
            <p>No personal or confidential data.</p>
            {voice.supported && (
              <p className="dictation-note">{DICTATION_DISCLOSURE}</p>
            )}
            {!unsavedPreview && config.history_enabled && (
              <p>
                Saved chats contain completed messages and expire{' '}
                {config.retention_days} days after their last update.
              </p>
            )}
            {(config.history_enabled || config.reviews_enabled) && (
              <p>
                Anyone with Lab access can{' '}
                {config.history_enabled && 'read, edit and delete saved chats'}
                {config.history_enabled && config.reviews_enabled && ', and '}
                {config.reviews_enabled &&
                  'read reviews and add requested evidence'}
                .
              </p>
            )}
            {config.agent_creation && (
              <p>
                {config.agent_creation.requires_operator_key
                  ? 'Agent setups are shared. Publishing or deleting an agent requires an operator key, not a user account.'
                  : 'Private presenter mode: anyone with Lab access can create or delete shared agents without a key. This is not a user account.'}
              </p>
            )}
          </details>
        </div>
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
                <div className="reply-limit">
                  <dt>Reply limit</dt>
                  <dd>
                    {turnCount} of {config.max_history_turns + 1} replies used
                  </dd>
                </div>
              </dl>
            </details>
          )}
          <span className="save-state">
            {saveStateText({
              isPreview: unsavedPreview,
              saved,
              dirty,
              draft,
            })}
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
