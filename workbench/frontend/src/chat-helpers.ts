import type { Turn } from './conversation-types'
import { saveFile } from './save-file'
import type { Agent, Config } from './workspace-config'

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
  const history = turns.flatMap((turn) => [
    { role: 'user', content: turn.question },
    { role: 'assistant', content: turn.result.text },
  ])
  const characters =
    history.reduce((total, message) => total + [...message.content].length, 0) +
    [...draft].length
  const payload = JSON.stringify({
    agent_id: selected,
    input: draft,
    history,
    thread,
  })
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
) {
  saveFile(
    'foundry-conversation.json',
    JSON.stringify({ agent: agent?.agent, turns, draft }, null, 2),
    'application/json',
  )
}
