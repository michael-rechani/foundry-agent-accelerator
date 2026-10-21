import { isPreviewId, type LibraryTemplate } from './library-catalog'
import type { Agent, CreationCapability } from './workspace-config'

export type LibraryTab = 'overview' | 'test' | 'results' | 'export'
export type LibraryViewMode = 'cards' | 'list'

export type ReadyAgent = { agent: Agent; recordId: string }

// One plain explanation of the "Not yet reviewed" label, used wherever it
// appears.
export const inProgressNote =
  "A person hasn't signed off on its test answers yet. Try it with sample data; answers may change."

// The one explanation of a library preview, used on the welcome screen, the
// side column and the top bar menu.
export const previewBlurb =
  "This preview runs on the Lab's model with sample lookups. Nothing is published, and preview chats aren't saved."

export const publishedBlurb =
  'This agent already has a published setup. Your message gives it a task; it does not change its tools or permanent instructions.'

export const createFromPreviewNote =
  "Preview chats can't be saved. Create this agent to save chats and take it to Foundry. Nothing is created until you confirm on the last step."

// What kind of agent this is, in the words the My agents tab uses.
export function agentKind(agent: Agent) {
  return isPreviewId(agent.id)
    ? 'Library preview'
    : agent.id.startsWith('created-')
      ? 'Made in this Lab'
      : 'Prebuilt agent'
}

// True for the `sample` readiness level, which the Lab labels "Not yet
// reviewed" until a person signs off on the agent's test answers.
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
