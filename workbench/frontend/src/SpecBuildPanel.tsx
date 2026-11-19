import { useEffect, useRef, useState } from 'react'
import { ArrowRight, LoaderCircle, Plus } from 'lucide-react'
import {
  CreationError,
  creationMessage,
  creationRequest,
  parseCreatedAgent,
  parseDraft,
  type CreatedAgent,
  type CreatePayload,
} from './agent-creation-client'
import { specGoal, type AgentSpec } from './agent-spec'
import { OperatorKeyField } from './OperatorKeyField'
import { PromptAgentTry } from './PromptAgentTry'
import type { SpecTests } from './SpecTestPanel'
import type { Agent, CreationCapability } from './workspace-config'

// What the chat needs to let a person finish an agent without leaving it.
export type SpecBuild = {
  capability: CreationCapability
  onCreated: (record: CreatedAgent) => void
  onChat: (agent: Agent) => void
  onOpenMade: () => void
}

const stages: Record<string, string> = {
  creating: 'Publishing to Foundry',
  failed: 'Publishing did not finish',
  interrupted: 'Publishing was interrupted',
}

function problemText(problem: unknown) {
  return problem instanceof Error && problem.name !== 'AbortError'
    ? problem.message
    : 'The request did not finish. Remote work may continue; check the same request before trying again.'
}

const promptOnlyId = 'prompt-only'

function readRecord(
  value: unknown,
  id: string,
  payload?: CreatePayload | null,
) {
  const record = parseCreatedAgent(value)
  if (
    record.id !== id ||
    (payload?.template_id === promptOnlyId &&
      (record.template_id !== promptOnlyId ||
        (record.status !== 'deleted' &&
          record.instructions !== payload.instructions))) ||
    (record.template_id === promptOnlyId &&
      record.status === 'ready' &&
      (!record.version || Object.keys(record.agent?.tools ?? {}).length))
  )
    throw new Error(
      'The saved response does not match this creation request. No ready agent can be confirmed.',
    )
  return record
}

export function SpecBuildPanel({
  spec,
  templateId,
  templateLabel,
  build,
  instructions = null,
  promptTry,
  disabled = false,
}: {
  spec: AgentSpec
  templateId?: string
  templateLabel?: string
  build: SpecBuild
  // Task instructions the person accepted while testing this draft. They
  // replace the prepared ones so what was tested is what gets published.
  instructions?: string | null
  promptTry?: SpecTests
  disabled?: boolean
}) {
  const { capability, onCreated } = build
  const [open, setOpen] = useState(false)
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [pending, setPending] = useState<CreatePayload | null>(null)
  const expected = useRef<CreatePayload | null>(null)
  const [record, setRecord] = useState<CreatedAgent | null>(null)
  const [pollPaused, setPollPaused] = useState(false)
  const [task, setTask] = useState(spec.instructions)
  const [trying, setTrying] = useState(false)
  const submitting = useRef(false)
  const keyField = useRef<HTMLInputElement>(null)
  const promptOnly = !templateId
  const validTask =
    [...task.trim()].length >= 10 &&
    [...task].length <= 6000 &&
    !task.includes('\0')
  const minutes = Math.ceil(capability.publication_timeout_seconds / 60)
  const running = record?.status === 'creating'
  const recordId = record?.id

  useEffect(() => {
    if (!recordId || !running || pollPaused) return
    const id = recordId
    const abort = new AbortController()
    let timer: number | undefined
    async function poll() {
      try {
        const next = readRecord(
          await creationRequest(`agents/${id}`, {}, abort.signal),
          id,
          expected.current,
        )
        if (abort.signal.aborted) return
        setRecord(next)
        onCreated(next)
        if (next.status === 'creating')
          timer = window.setTimeout(() => void poll(), 3000)
      } catch (problem) {
        if (!abort.signal.aborted) {
          setError(problemText(problem))
          setPollPaused(true)
        }
      }
    }
    timer = window.setTimeout(() => void poll(), 3000)
    return () => {
      abort.abort()
      window.clearTimeout(timer)
    }
  }, [recordId, running, pollPaused, onCreated])

  async function create() {
    if (
      submitting.current ||
      busy ||
      disabled ||
      trying ||
      !consent ||
      (promptOnly && !validTask)
    )
      return
    const key = capability.requires_operator_key
      ? (keyField.current?.value ?? '')
      : ''
    if (capability.requires_operator_key && key.length < 32) {
      setError(
        'Enter the operator key (at least 32 characters) to create a real agent. Ask the Lab operator if you do not have it.',
      )
      keyField.current?.focus()
      return
    }
    if (typeof crypto.randomUUID !== 'function') {
      setError(
        'Open the Lab over HTTPS, or a localhost development connection, before creating an agent.',
      )
      return
    }
    submitting.current = true
    setBusy(true)
    setError('')
    try {
      let payload = pending
      if (!payload && promptOnly) {
        payload = {
          idempotency_key: crypto.randomUUID(),
          template_id: promptOnlyId,
          name: spec.name,
          instructions: task,
          confirm_cost: true,
        }
        expected.current = payload
        setPending(payload)
      } else if (!payload) {
        const draft = parseDraft(
          await creationRequest('agent-drafts', {
            method: 'POST',
            body: JSON.stringify({
              goal: specGoal(spec),
              template_id: templateId,
            }),
          }),
        )
        if (draft.template_id !== templateId)
          throw new Error(
            'The prepared setup does not match the template this spec points to.',
          )
        const name = [...spec.name].length <= 80 ? spec.name : draft.name
        payload = {
          idempotency_key: crypto.randomUUID(),
          template_id: draft.template_id,
          name: name.trim() ? name : draft.name,
          instructions: instructions ?? draft.instructions,
          confirm_cost: true,
        }
        setPending(payload)
      }
      const created = readRecord(
        await creationRequest('agents', {
          method: 'POST',
          headers: key ? { 'X-Workbench-Creation-Key': key } : {},
          body: JSON.stringify(payload),
        }),
        `created-${payload.idempotency_key}`,
        payload,
      )
      if (keyField.current) keyField.current.value = ''
      setRecord(created)
      setPending(null)
      setPollPaused(false)
      onCreated(created)
    } catch (problem) {
      if (
        problem instanceof CreationError &&
        [400, 403, 413].includes(problem.status)
      )
        setPending(null)
      setError(problemText(problem))
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }

  async function refresh() {
    if (submitting.current || busy || (!pending && !record)) return
    submitting.current = true
    setBusy(true)
    setError('')
    try {
      const id = record?.id ?? `created-${pending?.idempotency_key}`
      const next = readRecord(
        await creationRequest(`agents/${id}`),
        id,
        expected.current,
      )
      setRecord(next)
      setPending(null)
      setPollPaused(false)
      onCreated(next)
    } catch (problem) {
      setError(problemText(problem))
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }

  async function chat() {
    if (!record?.agent || submitting.current) return
    if (!promptOnly) {
      build.onChat(record.agent)
      return
    }
    submitting.current = true
    setBusy(true)
    setError('')
    try {
      const current = readRecord(
        await creationRequest(`agents/${record.id}`),
        record.id,
        expected.current,
      )
      setRecord(current)
      onCreated(current)
      if (current.status === 'ready' && current.agent)
        build.onChat(current.agent)
    } catch (problem) {
      setError(problemText(problem))
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }

  if (!capability.enabled) return null

  if (record) {
    const ready = record.status === 'ready' ? record.agent : null
    return (
      <div className="spec-build" role="group" aria-label="Create this agent">
        <p className="spec-build-status" role="status">
          {ready ? (
            <>
              <strong>{record.name}</strong> is ready in Foundry.
            </>
          ) : running ? (
            <>
              <LoaderCircle size={16} className="spin" aria-hidden="true" />{' '}
              {stages.creating}. This can take up to {minutes} minute
              {minutes === 1 ? '' : 's'}. You can keep chatting here.
            </>
          ) : (
            <>
              {stages[record.status] ?? 'Publishing did not finish'}.{' '}
              {record.error ? creationMessage(record.error) : ''}
            </>
          )}
        </p>
        <div className="agent-spec-actions">
          {ready && (
            <button
              type="button"
              className="library-secondary"
              disabled={busy}
              onClick={() => void chat()}
            >
              Chat with it <ArrowRight size={16} aria-hidden="true" />
            </button>
          )}
          <button
            type="button"
            className="library-secondary"
            onClick={build.onOpenMade}
          >
            See it in Made in this Lab
          </button>
          {!ready && (!running || (promptOnly && pollPaused)) && (
            <button
              type="button"
              className="library-secondary"
              disabled={busy}
              onClick={() => void refresh()}
            >
              Check its status
            </button>
          )}
        </div>
        {promptOnly &&
          (record.status === 'interrupted' || record.status === 'failed') && (
            <p>
              To reconcile the existing request, open Made in this Lab and
              resume this saved agent. Do not create another one.
            </p>
          )}
        {ready && (
          <p className="agent-spec-note">
            It keeps costing money until an operator deletes it. Download the
            agent spec above to take it to your own Foundry project.
          </p>
        )}
        {error && (
          <p className="spec-build-error" role="alert">
            {error}
          </p>
        )}
      </div>
    )
  }

  if (!open)
    return (
      <div className="agent-spec-actions">
        <button
          type="button"
          className="library-secondary"
          disabled={disabled}
          onClick={() => setOpen(true)}
        >
          <Plus size={16} aria-hidden="true" />{' '}
          {promptOnly ? 'Review prompt-only agent' : 'Create this agent here'}
        </button>
      </div>
    )

  return (
    <div className="spec-build" role="group" aria-label="Create this agent">
      <h5>Create {spec.name} in Foundry</h5>
      {promptOnly ? (
        <>
          <p>
            Review the exact task instructions. The Lab adds only its fixed
            sample-data policy. This agent has no tools, lookups, or external
            sources. Use fictional inputs only.
          </p>
          <label className="spec-prompt-field">
            Task instructions
            <textarea
              rows={6}
              value={task}
              readOnly={busy || trying || !!pending}
              onChange={(event) => {
                setTask(event.target.value)
                setConsent(false)
              }}
            />
          </label>
          {!validTask && (
            <p>
              Enter 10 to 6,000 characters of task instructions without null
              characters.
            </p>
          )}
          {promptTry && !pending && (
            <PromptAgentTry
              key={task}
              instructions={task}
              timeoutMs={promptTry.timeoutMs}
              active={promptTry.active}
              disabled={!validTask || busy || disabled}
              onRunning={setTrying}
            />
          )}
          <p>
            Publishing creates a real agent in the shared Foundry project. It is
            not private to you.
          </p>
        </>
      ) : (
        <p>
          This publishes a real agent in the shared Foundry project from the{' '}
          <strong>{templateLabel}</strong> template, with your spec as its task.
          Nothing is created until you confirm below.
        </p>
      )}
      <ul>
        <li>
          Publishing takes up to {minutes} minute{minutes === 1 ? '' : 's'}. The
          Lab allows up to {capability.max_agents} created agents.
        </li>
        <li>
          The hosted agent keeps costing money until an operator deletes it.
          Closing this page does not stop it.
        </li>
        <li>Each chat message sent to it also uses the model.</li>
        {instructions && (
          <li>
            It will use the task instructions you accepted while testing (
            {[...instructions].length} characters), not the template&apos;s
            prepared text.
          </li>
        )}
      </ul>
      <OperatorKeyField
        inputRef={keyField}
        disabled={busy || disabled || trying}
        required={capability.requires_operator_key}
      />
      <label className="creation-consent">
        <input
          type="checkbox"
          checked={consent}
          disabled={busy || disabled || trying}
          onChange={(event) => setConsent(event.target.checked)}
        />
        <span>
          I confirm creating a shared Foundry agent can incur hosting, build and
          model charges.
        </span>
      </label>
      {pending && (
        <p className="agent-spec-note">
          This request may already be saved. Retry the same request or check its
          status; do not start another. Request ID:{' '}
          <code>{pending.idempotency_key}</code>
          {instructions !== null &&
            pending.instructions !== instructions &&
            ' The saved request keeps the instructions it was sent with, not the ones you accepted since.'}
        </p>
      )}
      {error && (
        <p className="spec-build-error" role="alert">
          {error}
        </p>
      )}
      <div className="agent-spec-actions">
        <button
          type="button"
          className="library-secondary spec-build-confirm"
          disabled={
            busy || disabled || trying || !consent || (promptOnly && !validTask)
          }
          onClick={() => void create()}
        >
          {busy ? (
            <LoaderCircle size={16} className="spin" aria-hidden="true" />
          ) : (
            <Plus size={16} aria-hidden="true" />
          )}
          {pending ? 'Retry same creation request' : 'Create in Foundry'}
        </button>
        {pending && (
          <button
            type="button"
            className="library-secondary"
            disabled={busy}
            onClick={() => void refresh()}
          >
            Check creation status
          </button>
        )}
        <button
          type="button"
          className="inline-link"
          disabled={busy || trying || !!pending}
          onClick={() => {
            setOpen(false)
            setError('')
            if (promptOnly) setConsent(false)
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
