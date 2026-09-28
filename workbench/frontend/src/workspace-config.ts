import { useEffect, useState } from 'react'
import { requestJson } from './request'

export type Agent = {
  id: string
  label: string
  category: string
  description: string
  guidance?: {
    input: string
    output: string
    limits: string
    delegation: string
    configuration: string
  }
  agent: string
  tools: Record<string, string>
  prompts: { label: string; text: string }[]
}

export type Config = {
  title: string
  mode: 'preview' | 'private'
  agents: Agent[]
  default_agent: string
  max_characters: number
  max_request_bytes: number
  max_history_turns: number
  review_timeout_ms: number
  history_timeout_ms: number
  history_enabled: boolean
  reviews_enabled?: boolean
  retention_days: number
  agent_creation?: CreationCapability
  library_preview?: LibraryPreviewCapability
  budget_alerts?: boolean
}

export type LibraryPreviewCapability = {
  enabled: boolean
  reason: string | null
  agent: string
}

export type CreationCapability = {
  enabled: boolean
  storage_enabled: boolean
  management_enabled?: boolean
  reason: string | null
  requires_operator_key: true
  max_agents: number
  publication_timeout_seconds: number
  model?: string | null
  models?: Record<string, string> | null
}

export function isObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

export function validAgent(value: unknown): value is Agent {
  return (
    isObject(value) &&
    ['id', 'label', 'category', 'description', 'agent'].every(
      (key) => typeof value[key] === 'string' && value[key].trim().length > 0,
    ) &&
    validGuidance(value.guidance) &&
    isObject(value.tools) &&
    Object.values(value.tools).every((target) => typeof target === 'string') &&
    Array.isArray(value.prompts) &&
    value.prompts.every(
      (prompt) =>
        isObject(prompt) &&
        typeof prompt.label === 'string' &&
        typeof prompt.text === 'string',
    )
  )
}

function validCreation(
  value: unknown,
): value is CreationCapability | undefined {
  return (
    value === undefined ||
    (isObject(value) &&
      typeof value.enabled === 'boolean' &&
      typeof value.storage_enabled === 'boolean' &&
      (value.management_enabled === undefined ||
        typeof value.management_enabled === 'boolean') &&
      value.requires_operator_key === true &&
      (value.reason === null || typeof value.reason === 'string') &&
      typeof value.max_agents === 'number' &&
      Number.isInteger(value.max_agents) &&
      value.max_agents >= 1 &&
      value.max_agents <= 20 &&
      typeof value.publication_timeout_seconds === 'number' &&
      Number.isInteger(value.publication_timeout_seconds) &&
      value.publication_timeout_seconds >= 30 &&
      value.publication_timeout_seconds <= 900 &&
      (value.model === undefined ||
        value.model === null ||
        typeof value.model === 'string') &&
      (value.models === undefined ||
        value.models === null ||
        (isObject(value.models) &&
          Object.values(value.models).every(
            (name) => typeof name === 'string' && name.trim().length > 0,
          ))) &&
      (!value.enabled || value.storage_enabled))
  )
}

function validLibraryPreview(
  value: unknown,
): value is LibraryPreviewCapability | undefined {
  return (
    value === undefined ||
    (isObject(value) &&
      typeof value.enabled === 'boolean' &&
      (value.reason === null || typeof value.reason === 'string') &&
      typeof value.agent === 'string' &&
      value.agent.trim().length > 0 &&
      value.enabled === (value.reason === null))
  )
}

function validGuidance(value: unknown): boolean {
  const keys = ['input', 'output', 'limits', 'delegation', 'configuration']
  return (
    value === undefined ||
    (!!value &&
      typeof value === 'object' &&
      !Array.isArray(value) &&
      Object.keys(value).length === keys.length &&
      keys.every((key) => key in value) &&
      Object.values(value).every(
        (text) =>
          typeof text === 'string' &&
          text.trim().length > 0 &&
          [...text.trim()].length <= 1200,
      ))
  )
}

function parseConfig(value: unknown): Config {
  if (!value || typeof value !== 'object') throw new Error('Invalid config')
  const config = value as Config
  const positive = (number: unknown) =>
    typeof number === 'number' && Number.isSafeInteger(number) && number > 0
  if (
    typeof config.title !== 'string' ||
    !config.title.trim() ||
    !['preview', 'private'].includes(config.mode) ||
    typeof config.history_enabled !== 'boolean' ||
    (config.reviews_enabled !== undefined &&
      typeof config.reviews_enabled !== 'boolean') ||
    !validCreation(config.agent_creation) ||
    (config.mode === 'preview' && config.agent_creation?.enabled) ||
    !validLibraryPreview(config.library_preview) ||
    (config.mode === 'preview' && config.library_preview?.enabled) ||
    (config.budget_alerts !== undefined &&
      typeof config.budget_alerts !== 'boolean') ||
    ![
      config.max_characters,
      config.max_request_bytes,
      config.review_timeout_ms,
      config.history_timeout_ms,
      config.retention_days,
    ].every(positive) ||
    !Number.isSafeInteger(config.max_history_turns) ||
    config.max_history_turns < 0 ||
    !Array.isArray(config.agents) ||
    !config.agents.length ||
    !config.agents.every(validAgent) ||
    new Set(config.agents.map((agent) => agent.id)).size !==
      config.agents.length ||
    !config.agents.some((agent) => agent.id === config.default_agent)
  )
    throw new Error('Invalid config')
  return config
}

export function useWorkspaceConfig() {
  const [config, setConfig] = useState<Config | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const abort = new AbortController()
    let active = true
    const timer = window.setTimeout(() => abort.abort(), 15000)
    void requestJson('/api/config', {}, abort.signal)
      .then(({ response, data }) => {
        if (!response.ok) throw new Error('Configuration unavailable')
        const parsed = parseConfig(data)
        if (active) {
          setConfig(parsed)
          document.title = parsed.title
        }
      })
      .catch(() => {
        if (active)
          setError(
            abort.signal.aborted
              ? 'Workspace configuration timed out.'
              : 'Workspace configuration unavailable or invalid.',
          )
      })
      .finally(() => window.clearTimeout(timer))
    return () => {
      active = false
      window.clearTimeout(timer)
      abort.abort()
    }
  }, [attempt])
  return {
    config,
    error,
    retry: () => {
      setError('')
      setAttempt((previous) => previous + 1)
    },
  }
}
