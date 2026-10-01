import { useEffect, useRef, useState } from 'react'
import { CircleAlert, Plus, RefreshCw } from 'lucide-react'
import type { Agent, CreationCapability } from './workspace-config'
import {
  CreationError,
  creationRequest,
  parseCreatedAgent,
  parseDraft,
  parseTemplates,
  type AgentDraft,
  type AgentTemplate,
  type CreatedAgent,
  type CreatedAgentState,
  type CreatePayload,
} from './agent-creation-client'
import { OperatorKeyField } from './OperatorKeyField'
import { CreationTaskForm } from './CreationTaskForm'
import { CreationSetupReview } from './CreationSetupReview'
import { CreatedAgentDetail, CreatedAgentList } from './CreatedAgents'
import './agent-creation.css'

function problemText(problem: unknown) {
  return problem instanceof Error && problem.name !== 'AbortError'
    ? problem.message
    : 'The request did not finish. Remote work may continue; check the same saved operation before retrying.'
}

export function AgentCreationWorkspace({
  capability,
  state,
  view,
  active,
  chatBusy,
  requestedTemplate,
  onView,
  onUse,
}: {
  capability: CreationCapability
  state: CreatedAgentState
  view: 'create' | 'created'
  active: boolean
  chatBusy: boolean
  requestedTemplate?: { id: string; key: number } | null
  onView: (view: 'create' | 'created') => void
  onUse: (agent: Agent) => void
}) {
  const [templates, setTemplates] = useState<AgentTemplate[]>([])
  const [templateAttempt, setTemplateAttempt] = useState(0)
  const [templateError, setTemplateError] = useState('')
  const [templateId, setTemplateId] = useState('')
  const [goal, setGoal] = useState('')
  const [draft, setDraft] = useState<AgentDraft | null>(null)
  const [name, setName] = useState('')
  const [instructions, setInstructions] = useState('')
  const workspace = useRef<HTMLElement>(null)
  const keyField = useRef<HTMLInputElement>(null)
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [pending, setPending] = useState<CreatePayload | null>(null)
  const [selected, setSelected] = useState<CreatedAgent | null>(null)
  const [pollPaused, setPollPaused] = useState(false)
  const [pollAttempt, setPollAttempt] = useState(0)
  const [handledRequest, setHandledRequest] = useState(0)
  const template = templates.find(
    (item) => item.id === (draft?.template_id || templateId),
  )
  const templateModel = template
    ? capability.models?.[template.model_profile.id] || capability.model
    : undefined
  const operationRunning =
    selected?.status === 'creating' || selected?.status === 'deleting'
  const selectedId = selected?.id
  const validSetup =
    !!name.trim() &&
    [...name].length <= 80 &&
    [...instructions.trim()].length >= 10 &&
    [...instructions].length <= 6000
  const canManage = capability.management_enabled ?? capability.enabled

  useEffect(() => {
    const abort = new AbortController()
    void creationRequest('agent-templates', {}, abort.signal)
      .then((value) => {
        if (!abort.signal.aborted) setTemplates(parseTemplates(value))
      })
      .catch((problem) => {
        if (!abort.signal.aborted) setTemplateError(problemText(problem))
      })
    return () => abort.abort()
  }, [templateAttempt])

  useEffect(() => {
    if (!goal && !draft && !pending) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [goal, draft, pending])

  const { update } = state
  useEffect(() => {
    if (!selectedId || !operationRunning || pollPaused) return
    const abort = new AbortController()
    let timer: number | undefined
    const identifier = selectedId
    async function poll() {
      try {
        const record = parseCreatedAgent(
          await creationRequest(`agents/${identifier}`, {}, abort.signal),
        )
        if (abort.signal.aborted) return
        update(record)
        setSelected(record)
        if (record.status === 'creating' || record.status === 'deleting')
          timer = window.setTimeout(() => void poll(), 3000)
      } catch (problem) {
        if (!abort.signal.aborted) {
          setError(problemText(problem))
          setPollPaused(true)
        }
      }
    }
    void poll()
    return () => {
      abort.abort()
      window.clearTimeout(timer)
    }
  }, [selectedId, operationRunning, pollPaused, pollAttempt, update])

  // A library selection preselects its template unless setup work is already in progress.
  if (requestedTemplate && handledRequest !== requestedTemplate.key) {
    const found = templates.find((item) => item.id === requestedTemplate.id)
    if (found) {
      setHandledRequest(requestedTemplate.key)
      if (!draft && !pending) {
        setTemplateId(found.id)
        if (
          !goal.trim() ||
          templates.some((entry) => entry.example_request === goal)
        )
          setGoal(found.example_request)
        setError('')
      }
    }
  }

  function pickTemplate(item: AgentTemplate) {
    setTemplateId(item.id)
    if (
      !goal.trim() ||
      templates.some((entry) => entry.example_request === goal)
    )
      setGoal(item.example_request)
    setError('')
  }

  async function prepare() {
    if (busy || [...goal.trim()].length < 10 || [...goal].length > 1200) return
    setBusy(true)
    setError('')
    try {
      const prepared = parseDraft(
        await creationRequest('agent-drafts', {
          method: 'POST',
          body: JSON.stringify({
            goal,
            ...(templateId ? { template_id: templateId } : {}),
          }),
        }),
      )
      if (!templates.some((item) => item.id === prepared.template_id))
        throw new Error(
          'The prepared setup does not match an available template.',
        )
      setDraft(prepared)
      setName(prepared.name)
      setInstructions(prepared.instructions)
      setConsent(false)
      workspace.current?.scrollTo({ top: 0 })
    } catch (problem) {
      setError(problemText(problem))
    } finally {
      setBusy(false)
    }
  }

  function accept(record: CreatedAgent) {
    update(record)
    setSelected(record)
    setPending(null)
    setDraft(null)
    setGoal('')
    setTemplateId('')
    setConsent(false)
    setPollPaused(false)
    setError('')
    workspace.current?.scrollTo({ top: 0 })
    onView('created')
  }

  async function publish() {
    if (!draft || !capability.enabled || !consent || !validSetup || busy) return
    const key = operatorKey()
    if (!key) return
    if (typeof crypto.randomUUID !== 'function') {
      setError(
        'Open the Lab over HTTPS, or a localhost development connection, before creating an agent.',
      )
      return
    }
    const payload = pending || {
      idempotency_key: crypto.randomUUID(),
      template_id: draft.template_id,
      name,
      instructions,
      confirm_cost: true as const,
    }
    setPending(payload)
    setBusy(true)
    setError('')
    try {
      accept(
        parseCreatedAgent(
          await creationRequest('agents', {
            method: 'POST',
            headers: { 'X-Workbench-Creation-Key': key },
            body: JSON.stringify(payload),
          }),
        ),
      )
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

  async function checkSubmission() {
    if (!pending || busy) return
    setBusy(true)
    setError('')
    try {
      accept(
        parseCreatedAgent(
          await creationRequest(`agents/created-${pending.idempotency_key}`),
        ),
      )
    } catch (problem) {
      setError(problemText(problem))
    } finally {
      setBusy(false)
    }
  }

  async function refreshSelected() {
    if (!selected || busy) return
    setBusy(true)
    setError('')
    try {
      const record = parseCreatedAgent(
        await creationRequest(`agents/${selected.id}`),
      )
      update(record)
      setSelected(record)
      setPollPaused(false)
      setPollAttempt((value) => value + 1)
    } catch (problem) {
      setError(problemText(problem))
      setPollPaused(true)
    } finally {
      setBusy(false)
    }
  }

  async function operate(action: 'resume' | 'delete') {
    if (!selected || busy || operationRunning) return
    const key = operatorKey()
    if (!key) return
    if (
      action === 'delete' &&
      !window.confirm(
        `Delete ${selected.name} from Foundry for everyone in this shared Lab? Export needed chats first. This stops the created runtime; it does not delete other saved chats.`,
      )
    )
      return
    setBusy(true)
    setError('')
    try {
      const record = parseCreatedAgent(
        await creationRequest(
          `agents/${selected.id}${action === 'resume' ? '/resume' : ''}`,
          {
            method: action === 'resume' ? 'POST' : 'DELETE',
            headers: {
              'X-Workbench-Creation-Key': key,
              'If-Match': selected._etag,
            },
          },
        ),
      )
      update(record)
      setSelected(record)
      setPollPaused(false)
    } catch (problem) {
      setError(problemText(problem))
    } finally {
      setBusy(false)
    }
  }

  function operatorKey() {
    const key = keyField.current?.value || ''
    if (key.length < 32) {
      setError(
        'Enter the operator key (at least 32 characters) before changing a Foundry resource.',
      )
      keyField.current?.focus()
      return null
    }
    return key
  }

  const keyInput = active && (
    <OperatorKeyField
      inputRef={keyField}
      disabled={!capability.enabled && !canManage}
    />
  )

  return (
    <main ref={workspace} className="creation-workspace" hidden={!active}>
      <div className="creation-heading">
        <div>
          <h1>{view === 'create' ? 'Create an agent' : 'Made in this Lab'}</h1>
          <p>
            {view === 'create'
              ? 'Start from a prepared template, describe the job, review the setup, then create a real Foundry agent to try. Use sample data only.'
              : 'Agents made in this shared Lab. Everyone with access can read their setups and use ready agents.'}
          </p>
        </div>
        {view === 'created' && (
          <div className="creation-actions">
            <button
              className="creation-secondary"
              disabled={state.loading || busy}
              onClick={() => {
                setSelected(null)
                setError('')
                void state.refresh()
              }}
            >
              <RefreshCw size={16} />
              Refresh agents
            </button>
            <button
              className="creation-primary"
              onClick={() => {
                setSelected(null)
                setError('')
                onView('create')
              }}
            >
              <Plus size={16} />
              Create agent
            </button>
          </div>
        )}
      </div>
      {error && (
        <div className="creation-error creation-error-pinned" role="alert">
          <CircleAlert size={18} />
          <p>{error}</p>
        </div>
      )}
      {view === 'create' ? (
        <>
          <ol className="creation-steps">
            <li>Describe the job</li>
            <li>Review name, instructions and tools</li>
            <li>Create in Foundry and try it</li>
          </ol>
          {!capability.enabled && (
            <p className="creation-notice">
              {capability.reason === 'local_preview'
                ? 'Local preview: prepare a setup only. No model calls, saved agents or Azure publication.'
                : 'Agent publication is disabled or not connected. You can prepare a setup; an operator must enable creation before it can be published.'}
            </p>
          )}
          {templateError ? (
            <div className="creation-error" role="alert">
              <p>{templateError}</p>
              <button
                onClick={() => {
                  setTemplateError('')
                  setTemplateAttempt((value) => value + 1)
                }}
              >
                Retry templates
              </button>
            </div>
          ) : !templates.length ? (
            <p role="status">Loading prepared templates...</p>
          ) : null}
          {!draft ? (
            <CreationTaskForm
              templates={templates}
              templateId={templateId}
              goal={goal}
              busy={busy}
              onPick={pickTemplate}
              onTemplateId={setTemplateId}
              onGoal={setGoal}
              onPrepare={() => void prepare()}
            />
          ) : (
            <CreationSetupReview
              draft={draft}
              template={template}
              templateModel={templateModel}
              name={name}
              instructions={instructions}
              consent={consent}
              pending={pending}
              busy={busy}
              publishEnabled={capability.enabled}
              validSetup={validSetup}
              operatorKey={keyInput}
              onChangeTask={() => {
                setDraft(null)
                setError('')
                setConsent(false)
              }}
              onName={setName}
              onInstructions={setInstructions}
              onConsent={setConsent}
              onPublish={() => void publish()}
              onCheck={() => void checkSubmission()}
            />
          )}
        </>
      ) : (
        <>
          {state.error && (
            <p className="creation-error" role="alert">
              {state.error}
            </p>
          )}
          {!capability.storage_enabled ? (
            <p className="creation-notice">
              Created-agent storage is not connected. No saved created agents
              can be listed here.
            </p>
          ) : selected ? (
            <CreatedAgentDetail
              record={selected}
              templates={templates}
              busy={busy}
              chatBusy={chatBusy}
              operationRunning={operationRunning}
              pollPaused={pollPaused}
              publishEnabled={capability.enabled}
              canManage={canManage}
              operatorKey={keyInput}
              onBack={() => {
                setSelected(null)
                setError('')
              }}
              onRefresh={() => void refreshSelected()}
              onUse={onUse}
              onOperate={(action) => void operate(action)}
            />
          ) : state.loading ? (
            <p role="status">Loading saved agents...</p>
          ) : (
            <CreatedAgentList
              records={state.records}
              error={state.error}
              onSelect={(record) => {
                setSelected(record)
                setError('')
                setPollPaused(false)
              }}
              onCreate={() => onView('create')}
            />
          )}
        </>
      )}
    </main>
  )
}
