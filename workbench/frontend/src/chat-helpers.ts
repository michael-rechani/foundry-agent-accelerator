import type { Turn } from './conversation-types'
import type { exportDemoChecks } from './demo-checks'
import { saveFile } from './save-file'
import type { Agent, Config } from './workspace-config'

// Where this conversation stands against shared history, in a few words.
export function saveStateText({
  isPreview,
  saved,
  dirty,
  draft,
}: {
  isPreview: boolean
  saved: boolean
  dirty: boolean
  draft: string
}) {
  if (isPreview) return 'Preview · not saved'
  if (!saved) return 'Not saved'
  if (dirty) return 'Unsaved changes'
  return draft ? 'Draft not saved' : 'Saved / shared'
}

// The request body for asking `input` after the given earlier turns.
export function requestPayload({
  turns,
  input,
  selected,
  thread,
}: {
  turns: Turn[]
  input: string
  selected: string
  thread: string | undefined
}) {
  const history = turns.flatMap((turn) => [
    { role: 'user', content: turn.question },
    { role: 'assistant', content: turn.result.text },
  ])
  return {
    history,
    payload: JSON.stringify({ agent_id: selected, input, history, thread }),
  }
}

// What a request would weigh, against the limits the Lab reports.
export function chatLimits({
  config,
  turns,
  draft,
  selected,
  thread,
}: {
  config: Config | null
  turns: Turn[]
  draft: string
  selected: string
  thread: string | undefined
}) {
  const { history, payload } = requestPayload({
    turns,
    input: draft,
    selected,
    thread,
  })
  const characters =
    history.reduce((total, message) => total + [...message.content].length, 0) +
    [...draft].length
  const requestBytes = new TextEncoder().encode(payload).length
  const limitReasons = config
    ? [
        characters > config.max_characters ? 'Character limit exceeded.' : '',
        requestBytes > config.max_request_bytes
          ? 'Request byte limit exceeded.'
          : '',
        turns.length > config.max_history_turns
          ? 'Conversation turn limit reached.'
          : '',
      ].filter(Boolean)
    : []
  const contextUsage = config
    ? Math.max(
        characters / config.max_characters,
        requestBytes / config.max_request_bytes,
        turns.length / (config.max_history_turns + 1),
      )
    : 0
  return {
    payload,
    characters,
    requestBytes,
    limitReasons,
    exceedsLimit: limitReasons.length > 0,
    contextUsage,
  }
}

export function exportConversation(
  agent: Agent | undefined,
  turns: Turn[],
  draft: string,
  demo?: ReturnType<typeof exportDemoChecks>,
) {
  saveFile(
    'foundry-conversation.json',
    JSON.stringify({ agent: agent?.agent, turns, draft, demo }, null, 2),
    'application/json',
  )
}
