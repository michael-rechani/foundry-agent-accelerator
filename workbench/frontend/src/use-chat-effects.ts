import { useEffect, useLayoutEffect, useRef } from 'react'
import type { View } from './ChatSidebar'
import type { Turn } from './conversation-types'
import type { DemoScenario } from './demo-scenarios'

// Warns before the tab closes while there is something that would be lost.
export function useUnsavedWarning(unsaved: boolean) {
  useEffect(() => {
    if (!unsaved) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [unsaved])
}

// Keeps the newest message in view. A fresh answer scrolls to its top, so the
// start of a long answer is the first thing read.
export function useConversationScroll(
  view: View,
  busy: boolean,
  turns: Turn[],
  activeDemo: DemoScenario | null,
) {
  const bottom = useRef<HTMLDivElement>(null)
  const latestAnswer = useRef<HTMLElement>(null)
  const lastScroll = useRef({ busy: false, turns: 0 })

  useEffect(() => {
    if (view !== 'chat') return
    const before = lastScroll.current
    lastScroll.current = { busy, turns: turns.length }
    const answered = before.busy && !busy && turns.length > before.turns
    if (activeDemo && !turns.length && !busy)
      bottom.current?.parentElement?.scrollTo({ top: 0 })
    else if (answered && latestAnswer.current)
      latestAnswer.current.scrollIntoView({ block: 'start' })
    else bottom.current?.scrollIntoView({ block: 'end' })
  }, [turns, busy, view, activeDemo])

  return { bottom, latestAnswer }
}

// The message box grows with what is typed.
export function useAutoGrowEditor(draft: string, view: View) {
  const editor = useRef<HTMLTextAreaElement>(null)

  useLayoutEffect(() => {
    const resize = () => {
      if (!editor.current) return
      editor.current.style.height = 'auto'
      editor.current.style.height = `${editor.current.scrollHeight}px`
    }
    resize()
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [draft, view])

  return editor
}
