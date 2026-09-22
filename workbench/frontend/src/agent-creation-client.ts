import { useCallback, useEffect, useRef, useState } from 'react'
import { requestJson } from './request'
import {
  isObject,
  validAgent,
  type Agent,
  type CreationCapability,
} from './workspace-config'

export type AgentTemplate = {
  id: string
  label: string
  description: string
  input: string
  output: string
  limits: string
  delegation: string
  instructions: string
  example_request: string
  sample_input: string
  tools: { name: string; description: string; simulated: boolean }[]
}
export type AgentDraft = {
  template_id: string
  name: string
  instructions: string
  goal: string
  source: 'template'
  sample_input: string
}
export type CreatePayload = {
  idempotency_key: string
  template_id: string
  name: string
  instructions: string
  confirm_cost: true
}
export type CreatedAgent = {
  id: string
  name: string
  template_id: string
  template_label?: string
  instructions: string
  runtime_name: string
  version: string | null
  model?: string
  status:
    | 'creating'
    | 'ready'
    | 'failed'
    | 'interrupted'
    | 'deleting'
    | 'deleted'
  stage: string
  operation?: 'create' | 'resume' | 'delete'
  created_at: string
  updated_at: string
  _etag: string
  error: string | null
  events: { name: string; at: string }[]
  agent: Agent | null
}

const messages: Record<string, string> = {
  template_required:
    'Choose the closest prepared template. This description does not identify one clear job.',
  invalid_setup:
    'Check the name, task instructions and input lengths. Tools, models and endpoints cannot be supplied here.',
  operator_access_required:
    'Enter a valid operator key. No new publication was authorized.',
  operator_permissions_required:
    'The Lab identity lacks the required Foundry permissions. An operator must review access; no roles are granted automatically.',
  creation_disabled:
    'New agent creation is not enabled in this Lab. Your draft is still available.',
  agent_limit_reached:
    'The Lab has reached its created-agent limit. Unconfirmed attempts count too; ask an operator to retire an agent.',
  agents_busy:
    'Another operation or too many requests are in progress. Check the saved state before retrying.',
  agents_unavailable:
    'Created-agent storage is unavailable. No saved state can be confirmed right now.',
  agent_changed:
    'This setup or operation changed. Refresh the saved record before acting again.',
  agent_not_found:
    'No saved agent record was found. An uncertain submission must be checked or retried with the same request ID.',
  agent_not_ready:
    'This agent is not ready to chat. Check its saved publication status.',
  agent_not_resumable:
    'This operation cannot resume as setup. Refresh it and check whether deletion is in progress.',
  agent_operation_running:
    'This agent already has an operation in progress. Refresh its status; do not submit another creation.',
  publication_failed:
    'Publication failed. Check the saved record and Foundry before starting another setup.',
  publication_unconfirmed:
    'The publication outcome is unconfirmed. Remote work may continue. Refresh or explicitly resume this saved setup, not a new creation.',
  publication_timeout:
    'The publication wait timed out. Remote work may continue and incur charges. Check or resume this saved setup.',
  runtime_failed:
    'The hosted version did not become active. An operator should inspect the version in Foundry.',
  runtime_changed:
    'The runtime bundle changed before this setup was published. Retire the unused record and prepare a new setup.',
  resource_changed:
    'The Foundry resource no longer matches this saved operation. Automatic changes were stopped; ask an operator to inspect it.',
  deletion_unconfirmed:
    'Deletion is not confirmed. The runtime may still exist and incur charges. Refresh or retry deletion of this same agent.',
  request_not_allowed: 'This browser request is not permitted.',
  request_too_large:
    'The setup exceeds the request size limit. Shorten the instructions.',
  agents_timeout:
    'The saved-state request timed out. Check the same operation before retrying.',
}

export function creationMessage(code: string) {
  return (
    messages[code] ||
    'The agent operation did not complete. Check its saved state before trying again.'
  )
}

export class CreationError extends Error {
  readonly code: string
  readonly status: number

  constructor(code: string, status: number) {
    super(creationMessage(code))
    this.code = code
    this.status = status
  }
}

export async function creationRequest(
  path: string,
  options: RequestInit = {},
  signal?: AbortSignal,
): Promise<unknown> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), 30000)
  const cancel = () => controller.abort()
  signal?.addEventListener('abort', cancel, { once: true })
  if (signal?.aborted) controller.abort()
  try {
    const headers = new Headers(options.headers)
    headers.set('X-Workbench-Request', '1')
    if (options.body) headers.set('Content-Type', 'application/json')
    const { response, data } = await requestJson(
      '/api/' + path,
      { ...options, headers },
      controller.signal,
    )
    if (!response.ok)
      throw new CreationError(
        isObject(data) && typeof data.error === 'string'
          ? data.error
          : 'operation_failed',
        response.status,
      )
    return data
  } finally {
    window.clearTimeout(timer)
    signal?.removeEventListener('abort', cancel)
  }
}

function strings(value: Record<string, unknown>, keys: string[]) {
  return keys.every((key) => typeof value[key] === 'string')
}

export function parseTemplates(value: unknown): AgentTemplate[] {
  if (
    !isObject(value) ||
    value.draft_mode !== 'template' ||
    !Array.isArray(value.templates) ||
    !value.templates.every(
      (item): item is AgentTemplate =>
        isObject(item) &&
        strings(item, [
          'id',
          'label',
          'description',
          'input',
          'output',
          'limits',
          'delegation',
          'instructions',
          'example_request',
          'sample_input',
        ]) &&
        Array.isArray(item.tools) &&
        item.tools.every(
          (tool) =>
            isObject(tool) &&
            strings(tool, ['name', 'description']) &&
            typeof tool.simulated === 'boolean',
        ),
    )
  )
    throw new Error(
      'The template response is invalid. Ask the Lab operator to check the server.',
    )
  if (
    !value.templates.length ||
    new Set(value.templates.map((item) => item.id)).size !==
      value.templates.length
  )
    throw new Error('The template list is empty or contains duplicate IDs.')
  return value.templates
}

export function parseDraft(value: unknown): AgentDraft {
  if (
    !isObject(value) ||
    value.source !== 'template' ||
    !strings(value, [
      'template_id',
      'name',
      'instructions',
      'goal',
      'sample_input',
    ])
  )
    throw new Error('The prepared setup response is invalid.')
  return value as AgentDraft
}

export function parseCreatedAgent(value: unknown): CreatedAgent {
  if (
    !isObject(value) ||
    !strings(value, [
      'id',
      'name',
      'template_id',
      'runtime_name',
      'status',
      'stage',
      'created_at',
      'updated_at',
      '_etag',
    ]) ||
    typeof value.instructions !== 'string' ||
    (value.status !== 'deleted' && !value.instructions.trim()) ||
    typeof value.id !== 'string' ||
    !/^created-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value.id) ||
    typeof value.status !== 'string' ||
    ![
      'creating',
      'ready',
      'failed',
      'interrupted',
      'deleting',
      'deleted',
    ].includes(value.status) ||
    !(value.version === null || typeof value.version === 'string') ||
    !(value.error === null || typeof value.error === 'string') ||
    !(
      value.operation === undefined ||
      ['create', 'resume', 'delete'].includes(String(value.operation))
    ) ||
    !(value.model === undefined || typeof value.model === 'string') ||
    !(
      value.template_label === undefined ||
      typeof value.template_label === 'string'
    ) ||
    !Array.isArray(value.events) ||
    !value.events.every(
      (event) => isObject(event) && strings(event, ['name', 'at']),
    ) ||
    !(value.agent === null || validAgent(value.agent)) ||
    (value.status === 'ready' &&
      (!validAgent(value.agent) ||
        value.agent.id !== value.id ||
        value.agent.agent !== value.runtime_name)) ||
    (value.status !== 'ready' && value.agent !== null)
  )
    throw new Error(
      'The saved agent response is invalid. No ready agent can be confirmed.',
    )
  return value as CreatedAgent
}

export function parseCreatedList(value: unknown): CreatedAgent[] {
  if (!isObject(value) || !Array.isArray(value.items))
    throw new Error('The created-agent list is invalid.')
  const records = value.items.map(parseCreatedAgent)
  if (new Set(records.map((record) => record.id)).size !== records.length)
    throw new Error('The created-agent list contains duplicate IDs.')
  return records
}

export function useCreatedAgents(capability?: CreationCapability) {
  const [records, setRecords] = useState<CreatedAgent[]>([])
  const [error, setError] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const mounted = useRef(true)
  const revision = useRef(0)
  useEffect(
    () => () => {
      mounted.current = false
    },
    [],
  )
  const update = useCallback((record: CreatedAgent) => {
    revision.current++
    setRecords((previous) =>
      [
        ...previous.filter((item) => item.id !== record.id),
        ...(record.status === 'deleted' ? [] : [record]),
      ].sort((left, right) => right.updated_at.localeCompare(left.updated_at)),
    )
  }, [])
  const load = useCallback(
    (signal?: AbortSignal) => {
      if (!capability?.storage_enabled) return Promise.resolve()
      const requestRevision = ++revision.current
      return creationRequest('agents', {}, signal)
        .then((value) => {
          const next = parseCreatedList(value)
          if (
            mounted.current &&
            !signal?.aborted &&
            requestRevision === revision.current
          ) {
            setRecords(next)
            setError('')
          }
        })
        .catch((problem: unknown) => {
          if (
            mounted.current &&
            !signal?.aborted &&
            requestRevision === revision.current
          )
            setError(
              problem instanceof Error
                ? problem.message
                : 'Created agents could not be loaded.',
            )
        })
        .finally(() => {
          if (mounted.current && !signal?.aborted) setLoaded(true)
        })
    },
    [capability?.storage_enabled],
  )
  const refresh = useCallback(async () => {
    setRefreshing(true)
    await load()
    if (mounted.current) setRefreshing(false)
  }, [load])
  useEffect(() => {
    mounted.current = true
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load])
  return {
    records: capability?.storage_enabled ? records : [],
    error,
    loading: refreshing || (!!capability?.storage_enabled && !loaded),
    refresh,
    update,
  }
}

export type CreatedAgentState = ReturnType<typeof useCreatedAgents>
