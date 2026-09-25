import { CheckCheck, LoaderCircle, Play } from 'lucide-react'
import {
  eventNames,
  statuses,
  type Review,
  type Run,
  type Source,
} from './review-client'
import { ReviewResults } from './ReviewResults'

type Tab = 'findings' | 'evidence' | 'activity'

function RunActivity({ run }: { run?: Run }) {
  return (
    <>
      <h2>Recorded activity</h2>
      {run?.error && <p>Run error: {run.error}</p>}
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
      {!run && <p className="review-empty">No execution recorded.</p>}
    </>
  )
}

export function ReviewDetail({
  review,
  run,
  runIndex,
  currentDraft,
  evidence,
  source,
  tab,
  additional,
  agentLabel,
  retentionDays,
  busy,
  onTab,
  onRunIndex,
  onSource,
  onAdditional,
  onExecute,
  onRecover,
  onAddEvidence,
}: {
  review: Review
  run?: Run
  runIndex: number
  currentDraft: boolean
  evidence: Source[]
  source?: Source
  tab: string
  additional: string
  agentLabel?: string
  retentionDays: number
  busy: boolean
  onTab: (tab: Tab) => void
  onRunIndex: (index: number) => void
  onSource: (id: string) => void
  onAdditional: (value: string) => void
  onExecute: () => void
  onRecover: () => void
  onAddEvidence: () => void
}) {
  return (
    <>
      <div className="review-meta">
        <span className={`review-status status-${review.status}`}>
          {statuses[review.status] || review.status}
        </span>
        <span>{review.runs.length}/4 runs</span>
        <span>Agent: {agentLabel || 'Agent unavailable in this catalog'}</span>
        <span>{retentionDays}-day retention after last update</span>
        {review.status === 'draft' && (
          <button
            className="review-primary"
            disabled={busy || review.runs.length >= 4}
            onClick={onExecute}
          >
            <Play size={15} />
            {review.runs.length ? 'Review again' : 'Run review'}
          </button>
        )}
      </div>
      {review.status === 'draft' && (
        <p className="review-next-step">
          {review.runs.length
            ? 'Your added information is saved but not checked yet. The results below are from the previous run. Choose Review again to check all the information together.'
            : 'Checklist and documents saved; no results yet. Check your input, then choose Run review.'}
        </p>
      )}
      {review.status === 'running' && (
        <div className="review-progress" role="status">
          <LoaderCircle className="spin" size={18} />
          Waiting for the agent&apos;s reply or its recovery window to expire.
          No new call will start automatically.
        </div>
      )}
      {['failed', 'interrupted'].includes(review.status) && (
        <div className="review-notice" role="alert">
          {review.runs.at(-1)?.error || 'Execution interrupted'}. Remote work
          may have completed. No automatic retry was made.
        </div>
      )}
      {review.status === 'interrupted' && (
        <div className="review-next-step">
          {review.runs.length > 0 && review.runs.length < 4 ? (
            <>
              <p>
                Recover the latest run using its saved checklist and documents.
                This starts a new agent call, not a continuation of the earlier
                call. The earlier call may still complete, so recovery may incur
                another model charge and uses one of the four runs.
              </p>
              <button
                className="review-primary"
                disabled={busy}
                onClick={onRecover}
              >
                Recover review
              </button>
            </>
          ) : (
            <p>
              {review.runs.length >= 4
                ? 'The four-run limit has been reached. This review cannot be recovered again.'
                : 'No saved run input is available for recovery.'}{' '}
              You can still inspect or export this record.
            </p>
          )}
        </div>
      )}
      <div className="review-tabs" role="tablist" aria-label="Review detail">
        {(['findings', 'evidence', 'activity'] as const).map((name) => (
          <button
            key={name}
            role="tab"
            aria-selected={tab === name}
            onClick={() => onTab(name)}
          >
            {
              {
                findings: 'Results',
                evidence: 'Original text',
                activity: 'Run details',
              }[name]
            }
          </button>
        ))}
        {!!review.runs.length && (
          <label className="run-picker">
            Run
            <select
              aria-label="Run version"
              value={runIndex < 0 ? review.runs.length - 1 : runIndex}
              onChange={(event) => onRunIndex(Number(event.target.value))}
            >
              {review.runs.map((attempt, index) => (
                <option value={index} key={attempt.id}>
                  {index + 1}
                  {index === review.runs.length - 1 ? ' (latest)' : ''}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <div className={`review-detail detail-${tab}`}>
        <section
          className="review-findings"
          aria-label={tab === 'activity' ? 'Run activity' : 'Review results'}
        >
          {tab === 'activity' ? (
            <RunActivity run={run} />
          ) : (
            <ReviewResults
              review={review}
              run={run}
              runIndex={runIndex}
              currentDraft={currentDraft}
              busy={busy}
              additional={additional}
              onCitation={(sourceId) => {
                onSource(sourceId)
                onTab('evidence')
              }}
              onAdditional={onAdditional}
              onAddEvidence={onAddEvidence}
            />
          )}
        </section>
        <aside className="review-evidence" aria-label="Original text">
          <div className="evidence-heading">
            <h2>Original text</h2>
            <select
              aria-label="Document"
              value={source?.id || ''}
              onChange={(event) => onSource(event.target.value)}
            >
              {evidence.map((item) => (
                <option key={item.id} value={item.id}>
                  Document {item.id.slice(4)} ({item.id})
                </option>
              ))}
            </select>
          </div>
          <span className="micro-label">
            {run && !currentDraft
              ? 'TEXT USED FOR THIS RUN'
              : 'YOUR SAVED TEXT'}
          </span>
          <pre>{source?.text}</pre>
        </aside>
      </div>
    </>
  )
}
