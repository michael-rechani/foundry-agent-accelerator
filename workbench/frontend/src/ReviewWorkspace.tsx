import { useEffect, useState } from 'react'
import {
  ArrowDownToLine,
  ArrowLeft,
  CircleAlert,
  Plus,
  RefreshCw,
} from 'lucide-react'
import type { Config } from './workspace-config'
import {
  reviewRequest,
  type Review,
  type ReviewItem,
  type Source,
} from './review-client'
import { ReviewGuide, ReviewIntro } from './ReviewGuide'
import { ReviewForm } from './ReviewForm'
import { ReviewDetail } from './ReviewDetail'
import { ReviewInbox } from './ReviewInbox'
import './reviews.css'

export function ReviewWorkspace({
  config,
  active,
}: {
  config: Config
  active: boolean
}) {
  const [items, setItems] = useState<ReviewItem[]>([])
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
    void reviewRequest('', 'GET', undefined, undefined, controller.signal)
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
      void reviewRequest(
        '/' + identifier,
        'GET',
        undefined,
        undefined,
        controller.signal,
      )
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
        const document = await reviewRequest(
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
    const data = await reviewRequest('')
    setItems(data.items)
    setCursor(data.cursor)
    setLoaded(true)
    if (selected) {
      setSelected(await reviewRequest('/' + selected.id))
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

  function startReview() {
    setCreating(true)
    setTitle('')
    setCriteria('')
    setSources([{ id: 'SRC-1', text: '' }])
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

  function createReview() {
    void perform(async () => {
      const document = await reviewRequest('', 'POST', {
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
  }

  function execute(review: Review) {
    void perform(async () =>
      accept(
        await reviewRequest(
          `/${review.id}/execute`,
          'POST',
          undefined,
          review._etag,
        ),
      ),
    )
  }

  function addEvidence(review: Review) {
    void perform(async () => {
      const next =
        Math.max(...review.evidence.map((item) => Number(item.id.slice(4)))) + 1
      accept(
        await reviewRequest(
          `/${review.id}/evidence`,
          'POST',
          { id: `SRC-${next}`, text: additional },
          review._etag,
        ),
      )
      setAdditional('')
    })
  }

  function loadMore(from: string) {
    void perform(async () => {
      const data = await reviewRequest('?cursor=' + encodeURIComponent(from))
      setItems((previous) => [...previous, ...data.items])
      setCursor(data.cursor)
    })
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
          {creating
            ? 'New document review'
            : selected
              ? selected.title
              : 'Document reviews'}
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
            <button className="review-primary" onClick={startReview}>
              <Plus size={16} />
              New review
            </button>
          )}
        </div>
      </header>
      {!selected && <ReviewIntro />}
      <ReviewGuide retentionDays={config.retention_days} />
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
        <ReviewForm
          title={title}
          criteria={criteria}
          sources={sources}
          agentLabel={reviewAgent?.label}
          busy={busy}
          enabled={enabled}
          onTitle={setTitle}
          onCriteria={setCriteria}
          onSources={setSources}
          onSample={sample}
          onSubmit={createReview}
        />
      ) : selected ? (
        <ReviewDetail
          review={selected}
          run={run}
          runIndex={runIndex}
          currentDraft={currentDraft}
          evidence={evidence}
          source={source}
          tab={tab}
          additional={additional}
          agentLabel={reviewAgent?.label}
          retentionDays={config.retention_days}
          busy={busy}
          onTab={setTab}
          onRunIndex={(index) => {
            setRunIndex(index)
            setSourceId('SRC-1')
          }}
          onSource={setSourceId}
          onAdditional={setAdditional}
          onExecute={() => execute(selected)}
          onAddEvidence={() => addEvidence(selected)}
        />
      ) : (
        <ReviewInbox
          items={items}
          loaded={loaded}
          enabled={enabled}
          cursor={cursor}
          query={query}
          filter={filter}
          busy={busy}
          onQuery={setQuery}
          onFilter={setFilter}
          onOpen={(id) =>
            void perform(async () => accept(await reviewRequest('/' + id)))
          }
          onMore={() => {
            if (cursor) loadMore(cursor)
          }}
        />
      )}
    </main>
  )
}
