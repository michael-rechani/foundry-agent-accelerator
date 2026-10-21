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

// A spec can become a real, billable agent from the chat, but only through the
// same steps as Create agent: a reviewed template, the operator key and an
// explicit cost confirmation. The setup is the template's reviewed
// instructions plus the spec as the task, so it never publishes free text.
export function SpecBuildPanel({
  spec,
  templateId,
  templateLabel,
  build,
}: {
  spec: AgentSpec
  templateId: string
  templateLabel: string
  build: SpecBuild
}) {
  const { capability, onCreated } = build
  const [open, setOpen] = useState(false)
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [pending, setPending] = useState<CreatePayload | null>(null)
  const [record, setRecord] = useState<CreatedAgent | null>(null)
  const [pollPaused, setPollPaused] = useState(false)
  const keyField = useRef<HTMLInputElement>(null)
  const minutes = Math.ceil(capability.publication_timeout_seconds / 60)
  const running = record?.status === 'creating'
  const recordId = record?.id

  useEffect(() => {
    if (!recordId || !running || pollPaused) return
    const abort = new AbortController()
    let timer: number | undefined
    async function poll() {
      try {
        const next = parseCreatedAgent(
          await creationRequest(`agents/${recordId}`, {}, abort.signal),
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
    if (busy || !consent) return
    const key = keyField.current?.value ?? ''
    if (key.length < 32) {
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
    setBusy(true)
    setError('')
    try {
      let payload = pending
      if (!payload) {
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
          instructions: draft.instructions,
          confirm_cost: true,
        }
        setPending(payload)
      }
      const created = parseCreatedAgent(
        await creationRequest('agents', {
          method: 'POST',
          headers: { 'X-Workbench-Creation-Key': key },
          body: JSON.stringify(payload),
        }),
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
      setBusy(false)
    }
  }

  async function refresh() {
    if (busy || (!pending && !record)) return
    setBusy(true)
    setError('')
    try {
      const next = parseCreatedAgent(
        await creationRequest(
          `agents/${record?.id ?? `created-${pending?.idempotency_key}`}`,
        ),
      )
      setRecord(next)
      setPending(null)
      setPollPaused(false)
      onCreated(next)
    } catch (problem) {
      setError(problemText(problem))
    } finally {
      setBusy(false)
    }
  }

  if (!capability.enabled) return null

  if (record) {
    const ready = record.status === 'ready' && record.agent
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
          {ready && record.agent && (
            <button
              type="button"
              className="library-secondary"
              onClick={() => build.onChat(record.agent as Agent)}
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
          {!ready && !running && (
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
          onClick={() => setOpen(true)}
        >
          <Plus size={16} aria-hidden="true" /> Create this agent here
        </button>
      </div>
    )

  return (
    <div className="spec-build" role="group" aria-label="Create this agent">
      <h5>Create {spec.name} in Foundry</h5>
      <p>
        This publishes a real agent in the shared Foundry project from the{' '}
        <strong>{templateLabel}</strong> template, with your spec as its task.
        Nothing is created until you confirm below.
      </p>
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
      </ul>
      <OperatorKeyField inputRef={keyField} disabled={busy} />
      <label className="creation-consent">
        <input
          type="checkbox"
          checked={consent}
          disabled={busy}
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
          disabled={busy || !consent}
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
          disabled={busy || !!pending}
          onClick={() => {
            setOpen(false)
            setError('')
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
