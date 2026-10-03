import type { Config, CreationCapability } from '../../src/workspace-config'
import { guidedReview } from '../fixtures'

export const foundryPortal =
  'https://ai.azure.com/nextgen/r/qqqqqru7TMyN3e7u7u7u7g,rg-lab,,lab-account,lab-project'

export const modeFor = (preview?: boolean): Config['mode'] =>
  preview ? 'preview' : 'private'

// The Lab configuration every spec starts from; each test overrides only what
// it is about.
export function labConfig(overrides: Partial<Config> = {}): Config {
  return {
    title: 'Foundry Agent Lab',
    mode: 'private',
    agents: [guidedReview],
    default_agent: guidedReview.id,
    max_characters: 60000,
    max_request_bytes: 65536,
    max_history_turns: 10,
    review_timeout_ms: 190000,
    history_timeout_ms: 45000,
    retention_days: 30,
    history_enabled: false,
    ...overrides,
  }
}

export function creationCapability(
  options: { preview?: boolean; disabled?: boolean } = {},
): CreationCapability {
  const unavailable = options.preview || options.disabled
  return {
    enabled: !unavailable,
    storage_enabled: !options.preview,
    management_enabled: !options.preview,
    reason: options.preview
      ? 'local_preview'
      : options.disabled
        ? 'not_enabled'
        : null,
    requires_operator_key: true,
    max_agents: 5,
    publication_timeout_seconds: 600,
    model: unavailable ? null : 'demo-model',
    models: unavailable
      ? null
      : {
          reasoning: 'demo-reasoning-model',
          extraction: 'demo-fast-model',
          tool_calling: 'demo-model',
        },
  }
}
