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
  waiting_input: 'Needs evidence',
  completed: 'Review complete',
  failed: 'Failed',
  interrupted: 'Interrupted',
}
const eventNames: Record<string, string> = {
  review_started: 'Review requested',
  specialist_receipts_checked: 'Specialist execution receipts checked',
  citations_checked: 'Source references and exact quotes checked',
  waiting_input: 'Additional evidence requested',
  completed: 'Findings recorded',
  failed: 'Review failed',
  interrupted: 'Execution interrupted',
}
const messages: Record<string, string> = {
  review_changed: 'This review changed. Refresh before continuing.',
  reviews_disabled: 'Review persistence is unavailable in this environment.',
  invalid_review: 'Check the evidence, criteria, and content limits.',
  review_not_runnable: 'This revision cannot be run again.',
  review_not_waiting: 'This review is not accepting more evidence.',
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
    if (dirty && !window.confirm('Discard unsaved review evidence?')) return
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
        text: 'Synthetic application APP-1: Twelve weekly workshops beginning October 1. A program lead and two facilitators will deliver the sessions. No budget is supplied.',
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
          {creating ? 'New review' : selected ? selected.title : 'Evidence reviews'}
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
      <p className="review-scope">
        Optional criteria-and-evidence workflow, separate from Chat. Requirements
        and proposal review is EXPERIMENTAL and reuses application review, not a
        new agent. Supplied inputs only; no live actions. People make decisions.
      </p>
      {error && (
        <div className="review-notice" role="alert">
          <CircleAlert size={18} />
          {error}
        </div>
      )}
      {!enabled && (
        <div className="review-notice">
          <CircleAlert size={17} />
          Reviews are not connected. Execution and saving are unavailable.
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
            <span>
              {
                config.agents.find((agent) => agent.id === config.default_agent)
                  ?.label
              }
            </span>
            <button
              type="button"
              className="review-secondary"
              onClick={sample}
              disabled={busy}
            >
              <FileText size={16} />
              Use synthetic example
            </button>
          </div>
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
            Criteria, one per line
            <textarea
              required
              rows={4}
              maxLength={12000}
              value={criteria}
              onChange={(event) => setCriteria(event.target.value)}
            />
          </label>
          <h2>Evidence</h2>
          {sources.map((item, index) => (
            <div className="source-editor" key={item.id}>
              <label>
                {item.id}
                <textarea
                  required
                  rows={5}
                  maxLength={12000}
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
                aria-label={`Remove ${item.id}`}
                title={`Remove ${item.id}`}
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
              Add source
            </button>
            <button className="review-primary" disabled={!enabled || busy}>
              <CheckCheck size={16} />
              Create review
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
            <span>30-day retention</span>
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
                {selected.runs.length ? 'Resume review' : 'Run review'}
              </button>
            )}
          </div>
          {selected.status === 'running' && (
            <div className="review-progress" role="status">
              <LoaderCircle className="spin" size={18} />
              Agent response pending
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
            {['findings', 'evidence', 'activity'].map((name) => (
              <button
                key={name}
                role="tab"
                aria-selected={tab === name}
                onClick={() => setTab(name)}
              >
                {name[0].toUpperCase() + name.slice(1)}
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
                tab === 'activity' ? 'Run activity' : 'Review findings'
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
                          ? 'Execution receipt checked at run time'
                          : 'Unverified execution'}
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
                        Citations checked against submitted text &middot;
                        Findings require human review
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
                                {citation.source_id}
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
                      <h2>Review criteria</h2>
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
                        <h2>Evidence requested</h2>
                        <ul>
                          {run?.result?.questions.map((question, index) => (
                            <li key={index}>{question}</li>
                          ))}
                        </ul>
                        <label>
                          Additional evidence
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
                          Save evidence
                        </button>
                        {selected.runs.length >= 4 && <p>Run limit reached.</p>}
                      </form>
                    )}
                </>
              )}
            </section>
            <aside className="review-evidence" aria-label="Source evidence">
              <div className="evidence-heading">
                <h2>Source evidence</h2>
                <select
                  aria-label="Evidence source"
                  value={source?.id || ''}
                  onChange={(event) => setSourceId(event.target.value)}
                >
                  {evidence.map((item) => (
                    <option key={item.id}>{item.id}</option>
                  ))}
                </select>
              </div>
              <span className="micro-label">
                {run && !currentDraft ? 'RUN SNAPSHOT' : 'SUBMITTED TEXT'}
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
              { label: 'Needs evidence', status: 'waiting_input' },
              { label: 'Running', status: 'running' },
              { label: 'Complete', status: 'completed' },
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
