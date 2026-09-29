import { ArrowRight, ClipboardList, FileText, Search } from 'lucide-react'
import { statuses, type ReviewItem } from './review-client'

export function ReviewInbox({
  items,
  loaded,
  enabled,
  cursor,
  query,
  filter,
  busy,
  onQuery,
  onFilter,
  onOpen,
  onMore,
}: {
  items: ReviewItem[]
  loaded: boolean
  enabled: boolean
  cursor: string | null
  query: string
  filter: string
  busy: boolean
  onQuery: (value: string) => void
  onFilter: (value: string) => void
  onOpen: (id: string) => void
  onMore: () => void
}) {
  const visible = items.filter(
    (item) =>
      (filter === 'all' || item.status === filter) &&
      item.title.toLowerCase().includes(query.toLowerCase()),
  )
  return (
    <>
      {enabled && (
        <dl className="review-overview" aria-label="Loaded review counts">
          {[
            { label: 'Loaded reviews', status: 'all' },
            { label: 'Needs information', status: 'waiting_input' },
            { label: 'Running', status: 'running' },
            { label: 'Results saved', status: 'completed' },
          ].map(({ label, status }) => (
            <div key={status} className={`overview-${status}`}>
              <dt>{label}</dt>
              <dd>
                {enabled && loaded
                  ? items.filter(
                      (item) => status === 'all' || item.status === status,
                    ).length
                  : '--'}
              </dd>
            </div>
          ))}
        </dl>
      )}
      <div className="review-filters">
        <label>
          <Search size={17} />
          <input
            aria-label="Search reviews"
            disabled={!enabled}
            placeholder="Search loaded reviews"
            value={query}
            onChange={(event) => onQuery(event.target.value)}
          />
        </label>
        <select
          aria-label="Review status"
          disabled={!enabled}
          value={filter}
          onChange={(event) => onFilter(event.target.value)}
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
            onClick={() => onOpen(item.id)}
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
              Try New review and its sample example: your checklist asks for a
              budget, but the application only lists workshop dates. The
              expected result is &ldquo;budget missing&rdquo;, not
              &ldquo;application rejected&rdquo;. This is an illustration, not a
              model result.
            </p>
          )}
        </div>
      )}
      {cursor && (
        <button className="review-secondary" disabled={busy} onClick={onMore}>
          Load more
          <ArrowRight size={16} />
        </button>
      )}
    </>
  )
}
