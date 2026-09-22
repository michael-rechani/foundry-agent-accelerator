import { useEffect, useState } from 'react'
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  CheckCheck,
  CircleAlert,
  ClipboardList,
  FileText,
  LoaderCircle,
  Play,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-react'
import type { Config } from './workspace-config'
import './reviews.css'

type Source = { id: string; text: string }
type Finding = {
  criterion_id: string
  assessment: 'supported' | 'gap' | 'conflict'
  explanation: string
  citations: { source_id: string; quote: string }[]
}
type Run = {
  id: string
  started_at: string
  elapsed_ms?: number
  error?: string
  input: { criteria: string[]; evidence: Source[] }
  events: { name: string; at: string }[]
  result?: { summary: string; findings: Finding[]; questions: string[] }
  receipts?: {
    tool: string
    agent: string
    verified: boolean
    call_id: string
  }[]
}
export type Review = {
  id: string
  title: string
  agent_id: string
  status: string
  updated_at: string
  _etag: string
  criteria: string[]
  evidence: Source[]
  runs: Run[]
}
type Item = Pick<Review, 'id' | 'title' | 'status' | 'updated_at'>
const statuses: Record<string, string> = {
  draft: 'Ready to run',
  running: 'Running',
  waiting_input: 'Needs information',
  completed: 'Results saved',
  failed: 'Failed',
  interrupted: 'Interrupted',
}
const eventNames: Record<string, string> = {
  review_started: 'Review requested',
  specialist_receipts_checked: 'Records of specialist calls checked',
  citations_checked: 'Quotes matched to your documents',
  waiting_input: 'Additional information requested',
  completed: 'Results saved',
  failed: 'Review failed',
  interrupted: 'Execution interrupted',
}
const messages: Record<string, string> = {
  review_changed: 'This review changed. Refresh before continuing.',
  reviews_disabled: 'Review persistence is unavailable in this environment.',
  invalid_review: 'Check your documents, checklist and length limits.',
  review_not_runnable: 'This revision cannot be run again.',
  review_not_waiting: 'This review is not accepting more information.',
  busy: 'Agent capacity is busy. Try again later.',
  reviews_busy: 'Review requests are limited. Try again in a minute.',
}

async function api(
  path: string,
  method = 'GET',
  body?: unknown,
  etag?: string,
  signal?: AbortSignal,
) {
  const response = await fetch(`/api/review-runs${path}`, {
    method,
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(40000)])
      : AbortSignal.timeout(40000),
    headers: {
      'X-Workbench-Request': '1',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(etag ? { 'If-Match': etag } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  })
  const data = await response.json()
  if (!response.ok)
    throw new Error(
      messages[data.error] ||
        'The request could not be confirmed. Refresh the inbox before repeating an action.',
    )
  return data
}

export function ReviewWorkspace({
  config,
  active,
}: {
  config: Config
  active: boolean
}) {
  const [items, setItems] = useState<Item[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [selected, setSelected] = useState<Review | null>(null)
  const [creating, setCreating] = useState(false)
  const [title, setTitle] = useState('')
  const [criteria, setCriteria] = useState('')
  const [sources, setSources] = useState<Source[]>([{ id: 'SRC-1', text: '' }])
  const [additional, setAdditional] = useState('')
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [tab, setTab] = useState('findings')
  const [sourceId, setSourceId] = useState('SRC-1')
  const [runIndex, setRunIndex] = useState(-1)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [pollVersion, setPollVersion] = useState(0)
  const enabled = config.reviews_enabled === true
  const reviewAgent = config.agents.find(
    (agent) => agent.id === (selected?.agent_id || config.default_agent),
  )
  const dirty =
    (creating &&
      !!(title || criteria || sources.some((source) => source.text))) ||
    !!additional
  const run = selected?.runs[runIndex < 0 ? selected.runs.length - 1 : runIndex]
  const currentDraft = selected?.status === 'draft' && runIndex < 0
  const evidence = currentDraft
    ? selected.evidence
    : run?.input.evidence || selected?.evidence || []
  const source = evidence.find((item) => item.id === sourceId) || evidence[0]
  const visible = items.filter(
    (item) =>
      (filter === 'all' || item.status === filter) &&
      item.title.toLowerCase().includes(query.toLowerCase()),
  )

  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  useEffect(() => {
    if (!enabled || !active) return
    const controller = new AbortController()
    void api('', 'GET', undefined, undefined, controller.signal)
      .then((data) => {
        setItems(data.items)
        setCursor(data.cursor)
        setLoaded(true)
      })
      .catch((problem) => {
        if (!controller.signal.aborted) setError(problem.message)
      })
    const identifier = window.location.hash.slice(1)
    if (/^review-[0-9a-f-]{36}$/.test(identifier)) {
      void api('/' + identifier, 'GET', undefined, undefined, controller.signal)
        .then(setSelected)
        .catch((problem) => {
          if (!controller.signal.aborted) setError(problem.message)
        })
    }
    return () => controller.abort()
  }, [enabled, active])

  useEffect(() => {
    if (!active || selected?.status !== 'running') return
    const controller = new AbortController()
    let timer: number
    const poll = async () => {
      try {
        const document = await api(
          '/' + selected.id,
          'GET',
          undefined,
          undefined,
          controller.signal,
        )
        if (controller.signal.aborted) return
        setSelected(document)
        setItems((previous) =>
          previous.map((item) => (item.id === document.id ? document : item)),
        )
        if (document.status === 'running') timer = window.setTimeout(poll, 3000)
      } catch (problem) {
        if (!controller.signal.aborted)
          setError(
            problem instanceof Error
              ? problem.message
              : 'Refresh to check the run.',
          )
      }
    }
    timer = window.setTimeout(poll, 1500)
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [active, selected?.id, selected?.status, pollVersion])

  async function perform(operation: () => Promise<void>) {
    setBusy(true)
    setError('')
    try {
      await operation()
    } catch (problem) {
      setError(
        problem instanceof Error
          ? problem.message
          : 'Request unavailable. Refresh before repeating an action.',
      )
    } finally {
      setBusy(false)
    }
  }

  function accept(document: Review) {
    setSelected(document)
    setRunIndex(-1)
    setSourceId('SRC-1')
    setTab('findings')
    setItems((previous) => [
      document,
      ...previous.filter((item) => item.id !== document.id),
    ])
    window.history.replaceState(null, '', '#' + document.id)
  }

  async function refresh() {
    const data = await api('')
    setItems(data.items)
    setCursor(data.cursor)
    setLoaded(true)
    if (selected) {
      setSelected(await api('/' + selected.id))
      setPollVersion((previous) => previous + 1)
    }
  }

  function leave() {
    if (dirty && !window.confirm('Discard unsaved review information?')) return
    setCreating(false)
    setSelected(null)
    setAdditional('')
    setError('')
    window.history.replaceState(null, '', window.location.pathname)
  }

  function sample() {
    setTitle('Community workshop application')
    setCriteria('Include a project budget.\nIdentify a delivery timeline.')
    setSources([
      {
        id: 'SRC-1',
        text: 'Fictional application APP-1: Twelve weekly workshops beginning October 1. A program lead and two facilitators will deliver the sessions. No budget is supplied.',
      },
    ])
  }

  function download() {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(selected, null, 2)], {
        type: 'application/json',
      }),
    )
    const link = document.createElement('a')
    link.href = url
    link.download = `${selected?.id}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <main className="review-workspace" hidden={!active}>
      <header className="review-heading">
        <h1>
          {creating ? 'New document review' : selected ? selected.title : 'Document reviews'}
        </h1>
        <div className="review-actions">
          {(creating || selected) && (
            <button
              className="review-icon"
              aria-label="Back to reviews"
              title="Back to reviews"
              onClick={leave}
              disabled={busy}
            >
              <ArrowLeft size={18} />
            </button>
          )}
          {selected && (
            <button
              className="review-icon"
              aria-label="Export review"
              title="Export review"
              onClick={download}
            >
              <ArrowDownToLine size={18} />
            </button>
          )}
          <button
            className="review-icon"
            aria-label="Refresh reviews"
            title="Refresh reviews"
            disabled={!enabled || busy}
            onClick={() => void perform(refresh)}
          >
            <RefreshCw size={18} className={busy ? 'spin' : ''} />
          </button>
          {!selected && !creating && (
            <button
              className="review-primary"
              onClick={() => {
                setCreating(true)
                setTitle('')
                setCriteria('')
                setSources([{ id: 'SRC-1', text: '' }])
              }}
            >
              <Plus size={16} />
              New review
            </button>
          )}
        </div>
      </header>
      {!selected && (
        <section className="review-intro" aria-label="Document review workflow">
          <p className="review-scope">
            Check the text you paste against your own checklist. See what is
            covered, what is missing and where documents disagree. Add more
            information and check again.
          </p>
          <ol className="review-steps">
            <li>Add a checklist and document text</li>
            <li>Run a review</li>
            <li>Read results beside the original text</li>
            <li>Add missing information and review again</li>
          </ol>
          <p className="review-hint">
            Chat is a conversation. A document review saves a separate check
            of each checklist item. Your Chat messages are not copied here,
            and review results are not sent back to Chat.
          </p>
        </section>
      )}
      <details className="review-guide">
        <summary>How to read results and where your work is saved</summary>
        <dl className="finding-key">
          <div>
            <dt>Supported</dt>
            <dd>The text you supplied backs up this checklist item. That does not prove the text is true.</dd>
          </div>
          <div>
            <dt>Gap</dt>
            <dd>There is not enough information. This does not mean the application has failed.</dd>
          </div>
          <div>
            <dt>Conflict</dt>
            <dd>Statements disagree. Ask which one applies instead of guessing.</dd>
          </div>
        </dl>
        <p>
          A matching quote shows what a document says, not whether it is true.
          These results do not approve applications or make business decisions
          for you.
        </p>
        <p>
          In a connected Lab, Create shared review saves your checklist and
          document text. Each run also saves a copy of its input, results,
          follow-up questions and records of tool calls. Unsubmitted drafts stay
          in this browser until you leave or reload. Chat saves completed messages
          only when you choose Save.
        </p>
        <p>
          Anyone who can open this Lab can read saved reviews and add requested
          information. Records are not private to you; there are no individual
          user accounts. Use made-up examples only. Reviews expire
          {' '}{config.retention_days} days after their last update; backup retention
          is separate. You cannot delete a review or edit its saved checklist here.
        </p>
        <p>
          You can run each review up to four times. Saving more information does
          not start the agent. Choose Review again to check your checklist
          against all the documents and information added so far. Each run is a
          new check, not a continuation of Chat.
        </p>
        <p>
          Requirements and proposal review is EXPERIMENTAL and uses the same
          application-checking agent. It cannot fetch documents or change a
          business system.
        </p>
      </details>
      {error && (
        <div className="review-notice" role="alert">
          <CircleAlert size={18} />
          {error}
        </div>
      )}
      {!enabled && (
        <div className="review-notice">
          <CircleAlert size={17} />
          Review execution and saving are unavailable in this environment. You
          can try a fictional draft without calling a model.
        </div>
      )}
      {creating ? (
        <form
          className="review-form"
          onSubmit={(event) => {
            event.preventDefault()
            void perform(async () => {
              const document = await api('', 'POST', {
                title,
                agent_id: config.default_agent,
                criteria: criteria
                  .split('\n')
                  .map((value) => value.trim())
                  .filter(Boolean),
                evidence: sources,
              })
              accept(document)
              setCreating(false)
              setTitle('')
              setCriteria('')
              setSources([{ id: 'SRC-1', text: '' }])
            })
          }}
        >
          <div className="review-form-bar">
            <div>
              <strong>Agent doing this check: {reviewAgent?.label || 'Agent unavailable in this catalog'}</strong>
              <p className="review-hint">Uses the Lab&apos;s default agent, not your Chat selection. No new agent is created.</p>
            </div>
            <button
              type="button"
              className="review-secondary"
              onClick={sample}
              disabled={busy}
            >
              <FileText size={16} />
              Use fictional example
            </button>
          </div>
          <p className="review-hint" id="review-input-guide">
            Paste made-up text directly; file uploads and fetching links are
            not available. Add up to 12 checklist items (1,000 characters each)
            and 12 documents (12,000 characters each), within 30,000 content
            characters in total.
          </p>
          <label>
            Review title
            <input
              required
              maxLength={80}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
          </label>
          <label>
            Checklist, one item per line
            <textarea
              required
              rows={4}
              maxLength={12000}
              aria-describedby="review-input-guide"
              placeholder="For example: Include a project budget."
              value={criteria}
              onChange={(event) => setCriteria(event.target.value)}
            />
          </label>
          <h2>Documents to check</h2>
          {sources.map((item, index) => (
            <div className="source-editor" key={item.id}>
              <label>
                Document {item.id.slice(4)} ({item.id})
                <textarea
                  required
                  rows={5}
                  maxLength={12000}
                  aria-describedby="review-input-guide"
                  placeholder="Paste a document or note here. Results will point back to this text."
                  value={item.text}
                  onChange={(event) =>
                    setSources((previous) =>
                      previous.map((source, position) =>
                        position === index
                          ? { ...source, text: event.target.value }
                          : source,
                      ),
                    )
                  }
                />
              </label>
              <button
                type="button"
                className="review-icon"
                aria-label={`Remove document ${item.id.slice(4)}`}
                title={`Remove document ${item.id.slice(4)}`}
                disabled={sources.length === 1 || busy}
                onClick={() =>
                  setSources((previous) =>
                    previous.filter((source) => source.id !== item.id),
                  )
                }
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
          <p className="review-hint">
            Create shared review saves this checklist and text for everyone who
            can open the Lab. It does not run the agent; choose Run review next.
          </p>
          <footer>
            <button
              type="button"
              className="review-secondary"
              disabled={sources.length >= 12 || busy}
              onClick={() =>
                setSources((previous) => [
                  ...previous,
                  {
                    id: `SRC-${Math.max(...previous.map((item) => Number(item.id.slice(4)))) + 1}`,
                    text: '',
                  },
                ])
              }
            >
              <Plus size={16} />
              Add document
            </button>
            <button className="review-primary" disabled={!enabled || busy}>
              <CheckCheck size={16} />
              Create shared review
            </button>
          </footer>
        </form>
      ) : selected ? (
        <>
          <div className="review-meta">
            <span className={`review-status status-${selected.status}`}>
              {statuses[selected.status] || selected.status}
            </span>
            <span>{selected.runs.length}/4 runs</span>
            <span>Agent: {reviewAgent?.label || 'Agent unavailable in this catalog'}</span>
            <span>{config.retention_days}-day retention after last update</span>
            {selected.status === 'draft' && (
              <button
                className="review-primary"
                disabled={busy || selected.runs.length >= 4}
                onClick={() =>
                  void perform(async () =>
                    accept(
                      await api(
                        `/${selected.id}/execute`,
                        'POST',
                        undefined,
                        selected._etag,
                      ),
                    ),
                  )
                }
              >
                <Play size={15} />
                {selected.runs.length ? 'Review again' : 'Run review'}
              </button>
            )}
          </div>
          {selected.status === 'draft' && (
            <p className="review-next-step">
              {selected.runs.length
                ? 'Your added information is saved but not checked yet. The results below are from the previous run. Choose Review again to check all the information together.'
                : 'Checklist and documents saved; no results yet. Check your input, then choose Run review.'}
            </p>
          )}
          {selected.status === 'running' && (
            <div className="review-progress" role="status">
              <LoaderCircle className="spin" size={18} />
              Waiting for the agent&apos;s reply
            </div>
          )}
          {['failed', 'interrupted'].includes(selected.status) && (
            <div className="review-notice" role="alert">
              {run?.error || 'Execution interrupted'}. Remote work may have
              completed. No automatic retry was made.
            </div>
          )}
          <div
            className="review-tabs"
            role="tablist"
            aria-label="Review detail"
          >
            {(['findings', 'evidence', 'activity'] as const).map((name) => (
              <button
                key={name}
                role="tab"
                aria-selected={tab === name}
                onClick={() => setTab(name)}
              >
                {{ findings: 'Results', evidence: 'Original text', activity: 'Run details' }[name]}
              </button>
            ))}
            {!!selected.runs.length && (
              <label className="run-picker">
                Run
                <select
                  aria-label="Run version"
                  value={runIndex < 0 ? selected.runs.length - 1 : runIndex}
                  onChange={(event) => {
                    setRunIndex(Number(event.target.value))
                    setSourceId('SRC-1')
                  }}
                >
                  {selected.runs.map((attempt, index) => (
                    <option value={index} key={attempt.id}>
                      {index + 1}
                      {index === selected.runs.length - 1 ? ' (latest)' : ''}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
          <div className={`review-detail detail-${tab}`}>
            <section
              className="review-findings"
              aria-label={
                tab === 'activity' ? 'Run activity' : 'Review results'
              }
            >
              {tab === 'activity' ? (
                <>
                  <h2>Recorded activity</h2>
                  <ol className="review-timeline">
                    {run?.events.map((event, index) => (
                      <li key={index}>
                        <CheckCheck size={16} />
                        <div>
                          {eventNames[event.name] || event.name}
                          <time>{new Date(event.at).toLocaleString()}</time>
                        </div>
                      </li>
                    ))}
                  </ol>
                  {run?.elapsed_ms !== undefined && (
                    <p>Elapsed: {(run.elapsed_ms / 1000).toFixed(1)}s</p>
                  )}
                  {run?.receipts?.map((receipt) => (
                    <div className="review-receipt" key={receipt.call_id}>
                      <strong>{receipt.tool}</strong>
                      <span>{receipt.agent}</span>
                      <small>
                        {receipt.verified
                          ? 'Call record checked when this run finished'
                          : 'Call not verified'}
                      </small>
                    </div>
                  ))}
                  {!run && (
                    <p className="review-empty">No execution recorded.</p>
                  )}
                </>
              ) : (
                <>
                  {run?.result ? (
                    <>
                      <h2>
                        {currentDraft
                          ? 'Previous run summary'
                          : 'Review summary'}
                      </h2>
                      <p className="review-summary">{run.result.summary}</p>
                      <span className="review-disclaimer">
                        Quotes point to your documents; they do not prove those
                        documents are true. Check the results yourself. They do
                        not approve applications or make business decisions.
                      </span>
                      {run.result.findings.map((finding) => (
                        <article
                          className="review-finding"
                          key={finding.criterion_id}
                        >
                          <div>
                            <span
                              className={`finding-label finding-${finding.assessment}`}
                            >
                              {finding.assessment}
                            </span>
                            <span className="micro-label">
                              {finding.criterion_id}
                            </span>
                          </div>
                          <h3>
                            {
                              run.input.criteria[
                                Number(finding.criterion_id.slice(5)) - 1
                              ]
                            }
                          </h3>
                          <p>{finding.explanation}</p>
                          {finding.citations.map((citation, index) => (
                            <blockquote key={index}>
                              <button
                                onClick={() => {
                                  setSourceId(citation.source_id)
                                  setTab('evidence')
                                }}
                              >
                                <FileText size={14} />
                                Document {citation.source_id.slice(4)} ({citation.source_id})
                                <ArrowRight size={14} />
                              </button>
                              <p>{citation.quote}</p>
                            </blockquote>
                          ))}
                        </article>
                      ))}
                    </>
                  ) : (
                    <>
                      <h2>Your checklist</h2>
                      <ol className="review-criteria">
                        {selected.criteria.map((criterion, index) => (
                          <li key={index}>
                            <span className="micro-label">
                              CRIT-{index + 1}
                            </span>
                            <p>{criterion}</p>
                          </li>
                        ))}
                      </ol>
                    </>
                  )}
                  {selected.status === 'waiting_input' &&
                    (runIndex < 0 || runIndex === selected.runs.length - 1) && (
                      <form
                        className="clarification-form"
                        onSubmit={(event) => {
                          event.preventDefault()
                          void perform(async () => {
                            const next =
                              Math.max(
                                ...selected.evidence.map((item) =>
                                  Number(item.id.slice(4)),
                                ),
                              ) + 1
                            accept(
                              await api(
                                `/${selected.id}/evidence`,
                                'POST',
                                { id: `SRC-${next}`, text: additional },
                                selected._etag,
                              ),
                            )
                            setAdditional('')
                          })
                        }}
                      >
                        <h2>More information needed</h2>
                        <ul>
                          {run?.result?.questions.map((question, index) => (
                            <li key={index}>{question}</li>
                          ))}
                        </ul>
                        <p className="review-hint">
                          Add the missing details or explain which statement
                          is correct. Save them, then choose Review again.
                        </p>
                        <label>
                          More information
                          <textarea
                            required
                            rows={5}
                            maxLength={12000}
                            value={additional}
                            onChange={(event) =>
                              setAdditional(event.target.value)
                            }
                          />
                        </label>
                        <button
                          className="review-primary"
                          disabled={
                            busy ||
                            selected.runs.length >= 4 ||
                            selected.evidence.length >= 12
                          }
                        >
                          <Plus size={16} />
                          Save added information
                        </button>
                        {selected.runs.length >= 4 && <p>Run limit reached.</p>}
                      </form>
                    )}
                </>
              )}
            </section>
            <aside className="review-evidence" aria-label="Original text">
              <div className="evidence-heading">
                <h2>Original text</h2>
                <select
                  aria-label="Document"
                  value={source?.id || ''}
                  onChange={(event) => setSourceId(event.target.value)}
                >
                  {evidence.map((item) => (
                    <option key={item.id} value={item.id}>Document {item.id.slice(4)} ({item.id})</option>
                  ))}
                </select>
              </div>
              <span className="micro-label">
                {run && !currentDraft ? 'TEXT USED FOR THIS RUN' : 'YOUR SAVED TEXT'}
              </span>
              <pre>{source?.text}</pre>
            </aside>
          </div>
        </>
      ) : (
        <>
          {enabled && <dl className="review-overview" aria-label="Loaded review counts">
            {[
              { label: 'Loaded reviews', status: 'all' },
              { label: 'Needs information', status: 'waiting_input' },
              { label: 'Running', status: 'running' },
              { label: 'Results saved', status: 'completed' },
            ].map(({ label, status }) => (
              <div key={status} className={`overview-${status}`}>
                <dt>{label}</dt>
                <dd>{enabled && loaded ? items.filter((item) => status === 'all' || item.status === status).length : '--'}</dd>
              </div>
            ))}
          </dl>}
          <div className="review-filters">
            <label>
              <Search size={17} />
              <input
                aria-label="Search reviews"
                disabled={!enabled}
                placeholder="Search loaded reviews"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <select
              aria-label="Review status"
              disabled={!enabled}
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
            >
              <option value="all">All statuses</option>
              {Object.entries(statuses).map(([value, label]) => (
                <option value={value} key={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="review-inbox">
            <div className="review-list-heading">
              <span>Review</span>
              <span>Status</span>
              <span>Updated</span>
            </div>
            {visible.map((item) => (
              <button
                className="review-row"
                key={item.id}
                disabled={busy}
                onClick={() =>
                  void perform(async () => accept(await api('/' + item.id)))
                }
              >
                <span>
                  <FileText size={18} />
                  {item.title}
                </span>
                <span className={`review-status status-${item.status}`}>
                  {statuses[item.status] || item.status}
                </span>
                <time>{new Date(item.updated_at).toLocaleDateString()}</time>
              </button>
            ))}
          </div>
          {!visible.length && (
            <div className="review-empty-state">
              <ClipboardList size={38} />
              <h2>
                {!enabled
                  ? 'Review storage unavailable'
                  : query || filter !== 'all'
                  ? 'No matching reviews'
                  : !loaded && enabled
                    ? 'Loading reviews'
                    : 'No reviews yet'}
              </h2>
              {!query && filter === 'all' && (loaded || !enabled) && (
                <p>
                  Try New review and its made-up example: your checklist asks
                  for a budget, but the application only lists workshop dates.
                  The expected result is &ldquo;budget missing&rdquo;, not
                  &ldquo;application rejected&rdquo;. This is an illustration,
                  not a model result.
                </p>
              )}
            </div>
          )}
          {cursor && (
            <button
              className="review-secondary"
              disabled={busy}
              onClick={() =>
                void perform(async () => {
                  const data = await api(
                    '?cursor=' + encodeURIComponent(cursor),
                  )
                  setItems((previous) => [...previous, ...data.items])
                  setCursor(data.cursor)
                })
              }
            >
              Load more
              <ArrowRight size={16} />
            </button>
          )}
        </>
      )}
    </main>
  )
}
