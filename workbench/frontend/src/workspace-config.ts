import { useEffect, useState } from 'react'
import { requestJson } from './request'

export type Agent = {
  id: string
  label: string
  category: string
  description: string
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
    !config.agents.every(
      (agent) =>
        agent &&
        ['id', 'label', 'category', 'description', 'agent'].every(
          (key) =>
            typeof agent[key as keyof Agent] === 'string' &&
            String(agent[key as keyof Agent]).trim(),
        ) &&
        agent.tools &&
        typeof agent.tools === 'object' &&
        !Array.isArray(agent.tools) &&
        Object.values(agent.tools).every(
          (target) => typeof target === 'string',
        ) &&
        Array.isArray(agent.prompts) &&
        agent.prompts.every(
          (prompt) =>
            prompt &&
            typeof prompt.label === 'string' &&
            typeof prompt.text === 'string',
        ),
    ) ||
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
