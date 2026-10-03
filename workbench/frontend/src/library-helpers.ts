import type { LibraryTemplate } from './library-catalog'
import type { Agent, CreationCapability } from './workspace-config'

export type LibraryTab = 'overview' | 'test' | 'results' | 'export'
export type LibraryViewMode = 'cards' | 'list'

export type ReadyAgent = { agent: Agent; recordId: string }

export function inProgress(template: LibraryTemplate) {
  return template.readiness.id === 'sample'
}

export function storesOpenChat(
  template: LibraryTemplate,
  preview?: Agent,
  ready?: ReadyAgent,
) {
  return template.tool_mode.id !== 'connected-required' && !!(preview || ready)
}

export function runTemplateChat(
  template: LibraryTemplate,
  preview: Agent | undefined,
  ready: ReadyAgent | undefined,
  onTest: (agent: Agent, input: string) => void,
) {
  if (template.tool_mode.id === 'connected-required') return
  if (preview) onTest(preview, template.sample_input)
  else if (ready) onTest(ready.agent, template.sample_input)
}

export function creationNote(capability?: CreationCapability) {
  return !capability
    ? 'Agent creation is not available in this Lab.'
    : capability.enabled
      ? 'Creating prepares a setup for review. Publishing it requires an operator key and incurs Foundry charges.'
      : capability.reason === 'local_preview'
        ? 'Local preview: you can prepare and review a setup, but nothing is published.'
        : 'Publishing is not enabled here. You can still prepare and review a setup.'
}
