import { useEffect, useRef, useState } from 'react'
import {
  ArrowRight,
  Check,
  CircleAlert,
  LoaderCircle,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react'
import type { Agent, CreationCapability } from './workspace-config'
import {
  CreationError,
  creationMessage,
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
import './agent-creation.css'

const stages: Record<string, string> = {
  queued: 'Setup saved',
  uploading: 'Publishing runtime code',
  provisioning: 'Waiting for Foundry',
  routing: 'Connecting the agent endpoint',
  ready: 'Ready to try',
  failed: 'Needs operator attention',
  interrupted: 'Outcome needs checking',
  deleting: 'Deleting from Foundry',
  deleted: 'Deletion confirmed',
}
const statuses: Record<CreatedAgent['status'], string> = {
  creating: 'Creating',
  ready: 'Ready to try',
  failed: 'Needs attention',
  interrupted: 'Check outcome',
  deleting: 'Deleting',
  deleted: 'Deleted',
}

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
  onView,
  onUse,
}: {
  capability: CreationCapability
  state: CreatedAgentState
  view: 'create' | 'created'
  active: boolean
  chatBusy: boolean
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
  const goalField = useRef<HTMLTextAreaElement>(null)
  const keyField = useRef<HTMLInputElement>(null)
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [pending, setPending] = useState<CreatePayload | null>(null)
  const [selected, setSelected] = useState<CreatedAgent | null>(null)
  const [pollPaused, setPollPaused] = useState(false)
  const [pollAttempt, setPollAttempt] = useState(0)
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
    <div className="creation-key">
      <label>
        Operator key
        <input
          type="password"
          autoComplete="off"
          ref={keyField}
          minLength={32}
          maxLength={256}
          disabled={!capability.enabled && !canManage}
        />
      </label>
      <p>
        Kept in memory for this view only, never sent to the model or saved with
        the agent.
      </p>
      <button
        className="inline-link"
        type="button"
        onClick={() => {
          if (keyField.current) keyField.current.value = ''
        }}
      >
        Clear operator key
      </button>
    </div>
  )

  return (
    <main ref={workspace} className="creation-workspace" hidden={!active}>
      <div className="creation-heading">
        <div>
          <h1>{view === 'create' ? 'Create an agent' : 'Created agents'}</h1>
          <p>
            {view === 'create'
              ? 'Describe a useful job, review its setup, then create a real Foundry agent to try. Use fictional public-sector, healthcare-administration or software-product tasks.'
              : 'Agents created in this shared Lab. Everyone with access can read their setups and use ready agents.'}
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
              New setup
            </button>
          </div>
        )}
      </div>
      {error && (
        <div className="creation-error" role="alert">
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
            <>
              <div
                className="creation-templates"
                aria-label="Prepared agent templates"
              >
                {templates.map((item) => (
                  <button
                    key={item.id}
                    className="creation-template"
                    aria-pressed={templateId === item.id}
                    disabled={busy}
                    onClick={() => {
                      setTemplateId(item.id)
                      if (
                        !goal.trim() ||
                        templates.some(
                          (entry) => entry.example_request === goal,
                        )
                      )
                        setGoal(item.example_request)
                      setError('')
                      goalField.current?.focus()
                    }}
                  >
                    <strong>{item.label}</strong>
                    <span>{item.description}</span>
                    <small>
                      {item.tools.length
                        ? 'Simulated read-only tools'
                        : 'Supplied text; no tools'}
                    </small>
                  </button>
                ))}
              </div>
              <form
                className="creation-form"
                onSubmit={(event) => {
                  event.preventDefault()
                  void prepare()
                }}
              >
                <label>
                  What should the agent help with?
                  <textarea
                    ref={goalField}
                    rows={3}
                    value={goal}
                    disabled={busy}
                    onChange={(event) => setGoal(event.target.value)}
                    placeholder="For example: Create an agent that summarizes fictional policy notices and identifies questions for staff."
                  />
                </label>
                <small>
                  {[...goal].length}/1200 characters; at least 10. Use made-up
                  details, not customer or patient information.
                </small>
                <label>
                  Prepared template
                  <select
                    value={templateId}
                    disabled={busy}
                    onChange={(event) => setTemplateId(event.target.value)}
                  >
                    <option value="">
                      Match my description, or ask me to choose
                    </option>
                    {templates.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
                <p className="creation-help">
                  Setup uses a prepared template and your task description. It
                  does not call a model, generate runtime code or save an agent.
                </p>
                <button
                  className="creation-primary"
                  disabled={
                    busy ||
                    !templates.length ||
                    [...goal.trim()].length < 10 ||
                    [...goal].length > 1200
                  }
                >
                  {busy ? (
                    <LoaderCircle size={16} className="spin" />
                  ) : (
                    <ArrowRight size={16} />
                  )}
                  Prepare setup
                </button>
              </form>
            </>
          ) : (
            <section className="creation-setup" aria-label="Review agent setup">
              <div className="creation-setup-heading">
                <h2>Review your agent setup</h2>
                <button
                  className="inline-link"
                  disabled={busy || !!pending}
                  onClick={() => {
                    setDraft(null)
                    setError('')
                    setConsent(false)
                  }}
                >
                  Change task or template
                </button>
              </div>
              <p>
                Prepared from <strong>{template?.label}</strong> and your
                description. No agent has been created yet.
              </p>
              {template && (
                <dl className="creation-explanation">
                  <div>
                    <dt>What you give it</dt>
                    <dd>{template.input}</dd>
                  </div>
                  <div>
                    <dt>What you get</dt>
                    <dd>{template.output}</dd>
                  </div>
                  <div>
                    <dt>How it works</dt>
                    <dd>{template.delegation}</dd>
                  </div>
                  <div>
                    <dt>What it cannot do</dt>
                    <dd>{template.limits}</dd>
                  </div>
                  <div>
                    <dt>Model</dt>
                    <dd>
                      {templateModel ? (
                        <code>{templateModel}</code>
                      ) : (
                        'Set by the Lab operator'
                      )}
                      {', chosen for '}
                      <strong>{template.model_profile.label}</strong>
                      {'. '}
                      {template.model_profile.reason}
                    </dd>
                  </div>
                </dl>
              )}
              <label>
                Agent name
                <input
                  value={name}
                  disabled={busy || !!pending}
                  onChange={(event) => setName(event.target.value)}
                />
              </label>
              <label>
                Task instructions
                <textarea
                  rows={7}
                  value={instructions}
                  disabled={busy || !!pending}
                  onChange={(event) => setInstructions(event.target.value)}
                />
              </label>
              <small>
                {[...instructions].length}/6000 instruction characters. Name: up
                to 80 characters.
              </small>
              <p className="creation-help">
                The template fixes the tools, runtime rules and model. A chat
                prompt can't change them.
              </p>
              {template?.tools.length ? (
                <ul className="creation-tool-list">
                  {template.tools.map((tool) => (
                    <li key={tool.name}>
                      <code>{tool.name}</code> - {tool.description}
                      {tool.simulated ? ' (SIMULATED)' : ''}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="creation-help">
                  No tools or external integrations.
                </p>
              )}
              <details className="creation-instructions">
                <summary>Fictional test input</summary>
                <pre>{draft.sample_input}</pre>
              </details>
              {keyInput}
              <label className="creation-consent">
                <input
                  type="checkbox"
                  checked={consent}
                  disabled={busy || !!pending}
                  onChange={(event) => setConsent(event.target.checked)}
                />
                <span>
                  I confirm creating a shared Foundry agent can incur hosting,
                  build and model charges. Closing this page does not stop the
                  runtime.
                </span>
              </label>
              {pending && (
                <p className="creation-notice">
                  This request may already be saved. Check its status or retry
                  the same request; do not create another copy. Request ID:{' '}
                  <code>{pending.idempotency_key}</code>
                </p>
              )}
              <div className="creation-actions">
                <button
                  className="creation-primary"
                  onClick={() => void publish()}
                  disabled={
                    busy || !capability.enabled || !validSetup || !consent
                  }
                >
                  {busy ? (
                    <LoaderCircle size={16} className="spin" />
                  ) : (
                    <Plus size={16} />
                  )}
                  {pending
                    ? 'Retry same creation request'
                    : 'Create in Foundry'}
                </button>
                {pending && (
                  <button
                    className="creation-secondary"
                    disabled={busy}
                    onClick={() => void checkSubmission()}
                  >
                    Check creation status
                  </button>
                )}
              </div>
            </section>
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
            <section
              className="creation-detail"
              aria-label="Created agent details"
            >
              <button
                className="inline-link"
                onClick={() => {
                  setSelected(null)
                  setError('')
                }}
              >
                Back to created agents
              </button>
              <h2>{selected.name}</h2>
              <div className="creation-actions">
                <span
                  className={`creation-status creation-status-${selected.status}`}
                >
                  {statuses[selected.status]}
                </span>
                <button
                  className="creation-secondary"
                  disabled={busy}
                  onClick={() => void refreshSelected()}
                >
                  <RefreshCw size={16} />
                  Refresh status
                </button>
                {selected.agent && (
                  <button
                    className="creation-primary"
                    disabled={chatBusy}
                    onClick={() => {
                      if (selected.agent) onUse(selected.agent)
                    }}
                  >
                    <ArrowRight size={16} />
                    Try in Chat
                  </button>
                )}
              </div>
              {operationRunning && (
                <p role="status" className="creation-progress">
                  <LoaderCircle size={18} className="spin" />
                  {stages[selected.stage] || 'Operation in progress'}
                  {pollPaused
                    ? ' - automatic checks paused; refresh explicitly.'
                    : '. This can take several minutes. You can return to this saved record.'}
                </p>
              )}
              {selected.error && (
                <p className="creation-notice">
                  {creationMessage(selected.error)}
                </p>
              )}
              {selected.status === 'ready' && (
                <p className="creation-help">
                  Foundry reported an active runtime and the route was checked.
                  Send a sample in Chat to test the answer; this is not a
                  model-quality certification.
                </p>
              )}
              <dl className="creation-runtime">
                <div>
                  <dt>Template</dt>
                  <dd>
                    {selected.template_label ||
                      templates.find((item) => item.id === selected.template_id)
                        ?.label ||
                      selected.template_id}
                  </dd>
                </div>
                <div>
                  <dt>Foundry agent name</dt>
                  <dd>
                    <code>{selected.runtime_name}</code>
                  </dd>
                </div>
                <div>
                  <dt>Version</dt>
                  <dd>{selected.version || 'Not confirmed yet'}</dd>
                </div>
                {selected.model && (
                  <div>
                    <dt>Model deployment</dt>
                    <dd>
                      <code>{selected.model}</code>
                      {selected.model_profile &&
                        `, chosen for ${selected.model_profile.label}`}
                    </dd>
                  </div>
                )}
              </dl>
              {selected.instructions && (
                <details className="creation-instructions">
                  <summary>Saved task instructions</summary>
                  <pre>{selected.instructions}</pre>
                </details>
              )}
              <details className="creation-timeline">
                <summary>Publication activity</summary>
                <ol>
                  {selected.events.map((event, index) => (
                    <li key={`${index}-${event.at}`}>
                      {stages[event.name] || event.name}
                      <time>{new Date(event.at).toLocaleString()}</time>
                    </li>
                  ))}
                </ol>
              </details>
              {!operationRunning && selected.status !== 'deleted' && (
                <>
                  {keyInput}
                  <div className="creation-actions">
                    {['failed', 'interrupted'].includes(selected.status) &&
                      selected.operation !== 'delete' &&
                      selected.error !== 'deletion_unconfirmed' && (
                        <button
                          className="creation-secondary"
                          disabled={busy || !capability.enabled}
                          onClick={() => void operate('resume')}
                        >
                          Resume setup
                        </button>
                      )}
                    <button
                      className="creation-secondary"
                      disabled={busy || !canManage}
                      onClick={() => void operate('delete')}
                    >
                      <Trash2 size={16} />
                      Delete created agent
                    </button>
                  </div>
                  <p className="creation-help">
                    An operator can delete this created runtime for everyone.
                    Export needed chats first. Existing catalog agents are not
                    affected.
                  </p>
                </>
              )}
              {selected.status === 'deleted' && (
                <p className="creation-notice">
                  <Check size={16} />
                  Deletion was confirmed. The saved name and instructions were
                  cleared.
                </p>
              )}
            </section>
          ) : state.loading ? (
            <p role="status">Loading saved agents...</p>
          ) : state.records.length ? (
            <div className="created-agent-list">
              {state.records.map((record) => (
                <button
                  className="created-agent-row"
                  key={record.id}
                  onClick={() => {
                    setSelected(record)
                    setError('')
                    setPollPaused(false)
                  }}
                >
                  <span>
                    <strong>{record.name}</strong>
                    <small>{record.template_label || record.template_id}</small>
                  </span>
                  <span
                    className={`creation-status creation-status-${record.status}`}
                  >
                    {statuses[record.status]}
                  </span>
                  <ArrowRight size={16} />
                </button>
              ))}
            </div>
          ) : (
            !state.error && (
              <div className="creation-empty">
                <h2>No created agents yet</h2>
                <p>
                  Prepare a fictional task setup first. It appears here only
                  after the server has saved a creation request.
                </p>
                <button
                  className="creation-primary"
                  onClick={() => onView('create')}
                >
                  Prepare an agent
                </button>
              </div>
            )
          )}
        </>
      )}
    </main>
  )
}
