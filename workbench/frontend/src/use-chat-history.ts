import { useState } from 'react'
import {
  creationRequest,
  parseCreatedAgent,
  type CreatedAgentState,
} from './agent-creation-client'
import type { View } from './ChatSidebar'
import type { SavedChat } from './HistoryView'
import { useHistoryClient } from './history-client'
import type { Conversation } from './use-conversation'
import type { Agent, Config } from './workspace-config'

// Shared history: the list of saved chats, and saving, opening and deleting
// them. Each action keeps the local messages if it fails.
export function useChatHistory({
  config,
  conversation,
  availableAgents,
  createdAgents,
  setView,
  setNotice,
}: {
  config: Config | null
  conversation: Conversation
  availableAgents: Agent[]
  createdAgents: CreatedAgentState
  setView: (view: View) => void
  setNotice: (notice: string) => void
}) {
  const { selected, draft, turns, busy, saved, dirty, setSaved, setDirty } =
    conversation
  const [historyBusy, setHistoryBusy] = useState(false)
  const [savedChats, setSavedChats] = useState<SavedChat[]>([])
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [cursor, setCursor] = useState<string | null>(null)
  const historyRequest = useHistoryClient(config?.history_timeout_ms)

  async function listHistory(more = false) {
    if (historyBusy) return
    setView('history')
    setHistoryBusy(true)
    setNotice('')
    try {
      const data = await historyRequest(
        more && cursor ? `?cursor=${encodeURIComponent(cursor)}` : '',
      )
      setSavedChats((previous) =>
        more ? [...previous, ...data.items] : data.items,
      )
      setHistoryLoaded(true)
      setCursor(data.cursor)
    } catch (problem) {
      setNotice(
        problem instanceof Error ? problem.message : 'History unavailable.',
      )
    } finally {
      setHistoryBusy(false)
    }
  }

  async function saveChat() {
    if (!turns.length || busy || historyBusy) return
    setHistoryBusy(true)
    try {
      const data = await historyRequest(saved ? `/${saved.id}` : '', {
        method: saved ? 'PUT' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(saved ? { 'If-Match': saved._etag } : {}),
        },
        body: JSON.stringify({
          agent_id: selected,
          turns: turns.map(({ question, result }) => ({ question, result })),
        }),
      })
      setSaved(data)
      setDirty(false)
      setNotice(
        `Completed replies saved to shared history for ${config?.retention_days} days. Drafts are not saved.`,
      )
    } catch (problem) {
      setNotice(problem instanceof Error ? problem.message : 'Save failed.')
    } finally {
      setHistoryBusy(false)
    }
  }

  async function openChat(item: SavedChat) {
    if (
      busy ||
      historyBusy ||
      ((dirty || draft) &&
        !window.confirm(
          'Open this conversation and discard unsaved local messages?',
        ))
    )
      return
    setHistoryBusy(true)
    try {
      const data = await historyRequest(`/${item.id}`)
      if (
        !availableAgents.some((entry) => entry.id === data.agent_id) &&
        data.agent_id.startsWith('created-')
      ) {
        const record = parseCreatedAgent(
          await creationRequest(`agents/${data.agent_id}`),
        )
        if (!record.agent)
          throw new Error(
            'The saved conversation uses an agent that is no longer ready.',
          )
        createdAgents.update(record)
      }
      conversation.restore(
        data.agent_id,
        { id: data.id, _etag: data._etag },
        data.turns,
      )
      setNotice('')
      setView('chat')
    } catch (problem) {
      setNotice(problem instanceof Error ? problem.message : 'Open failed.')
    } finally {
      setHistoryBusy(false)
    }
  }

  async function deleteChat(item: SavedChat) {
    if (
      busy ||
      historyBusy ||
      !window.confirm(
        'Delete this conversation from shared history for everyone?',
      )
    )
      return
    setHistoryBusy(true)
    try {
      const current = await historyRequest(`/${item.id}`)
      await historyRequest(`/${item.id}`, {
        method: 'DELETE',
        headers: { 'If-Match': current._etag },
      })
      setSavedChats((previous) =>
        previous.filter((chat) => chat.id !== item.id),
      )
      if (saved?.id === item.id) {
        setSaved(null)
        setDirty(turns.length > 0)
      }
      setNotice('Deleted from shared history.')
    } catch (problem) {
      setNotice(problem instanceof Error ? problem.message : 'Delete failed.')
    } finally {
      setHistoryBusy(false)
    }
  }

  return {
    historyBusy,
    savedChats,
    historyLoaded,
    cursor,
    listHistory,
    saveChat,
    openChat,
    deleteChat,
  }
}
