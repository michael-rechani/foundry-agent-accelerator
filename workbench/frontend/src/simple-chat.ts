import { useSyncExternalStore } from 'react'

export const simpleChatKey = 'ai-foundry-lab-simple-chat'

const listeners = new Set<() => void>()
let fallback = true

export function loadSimpleChat(): boolean {
  try {
    return localStorage.getItem(simpleChatKey) !== '0'
  } catch {
    return fallback
  }
}

export function saveSimpleChat(on: boolean) {
  fallback = on
  try {
    localStorage.setItem(simpleChatKey, on ? '1' : '0')
  } catch {
    // Storage can be unavailable; the choice still applies until reload.
  }
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  const sync = (event: StorageEvent) => {
    if (event.key === simpleChatKey) listener()
  }
  window.addEventListener('storage', sync)
  return () => {
    listeners.delete(listener)
    window.removeEventListener('storage', sync)
  }
}

// The welcome screen without the guide, starters and examples: just the
// agent's name and the message box. Saved in this browser only.
export function useSimpleChat(): [boolean, (on: boolean) => void] {
  const on = useSyncExternalStore(subscribe, loadSimpleChat, () => true)
  return [on, saveSimpleChat]
}
