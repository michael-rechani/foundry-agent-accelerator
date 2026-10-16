import { useState } from 'react'
import type { ChatFailure } from './chat-failure'
import type { Turn } from './conversation-types'
import type { DemoScenario } from './demo-scenarios'

export type SavedVersion = { id: string; _etag: string }

// Identifies one conversation so the server can reuse its warm agent session.
const newThread = () =>
  typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : undefined

// The state of the chat on screen: which agent, the messages so far, the draft
// and whether it has been saved to shared history.
export function useConversation(defaultAgent: string | undefined) {
  const [selectedId, setSelected] = useState('')
  const selected = selectedId || defaultAgent || ''
  const [draft, setDraft] = useState('')
  // The text the app put in the message box, so a draft the user never touched
  // isn't counted as work they would lose.
  const [seed, setSeed] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [pending, setPending] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ChatFailure | null>(null)
  const [saved, setSaved] = useState<SavedVersion | null>(null)
  const [dirty, setDirty] = useState(false)
  const [activeDemo, setActiveDemo] = useState<DemoScenario | null>(null)
  const [thread, setThread] = useState(newThread)

  function reset(agentId: string, initialDraft = '') {
    setSelected(agentId)
    setThread(newThread())
    setTurns([])
    setDraft(initialDraft)
    setSeed(initialDraft)
    setPending('')
    setError(null)
    setSaved(null)
    setDirty(false)
    setActiveDemo(null)
  }

  function prefill(text: string) {
    setDraft(text)
    setSeed(text)
  }

  function restore(agentId: string, version: SavedVersion, stored: Turn[]) {
    setSaved(version)
    setSelected(agentId)
    setThread(newThread())
    setTurns(stored.map((turn) => ({ ...turn, stored: true })))
    setDirty(false)
    setDraft('')
    setSeed('')
    setPending('')
    setError(null)
    setActiveDemo(null)
  }

  return {
    selected,
    draft,
    seed,
    turns,
    pending,
    busy,
    error,
    saved,
    dirty,
    activeDemo,
    thread,
    setDraft,
    setTurns,
    setPending,
    setBusy,
    setError,
    setSaved,
    setDirty,
    setActiveDemo,
    reset,
    prefill,
    restore,
  }
}

export type Conversation = ReturnType<typeof useConversation>
