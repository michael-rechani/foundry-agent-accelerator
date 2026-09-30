import type { ComponentType } from 'react'

export type MarkdownRenderer = ComponentType<{ text: string }>

let renderer: MarkdownRenderer | undefined
let loading: Promise<MarkdownRenderer | undefined> | undefined

export const loadedMarkdown = () => renderer

// The formatter is a separate script. Chat starts fetching it on the first
// Send, so it is usually ready by the time the answer arrives.
export function preloadMarkdown() {
  loading ??= import('./MarkdownText').then(
    (module) => (renderer = module.default),
    () => {
      loading = undefined
      return undefined
    },
  )
  return loading
}
