import { Search } from 'lucide-react'
import type { LibraryViewMode } from './library-helpers'

export function LibrarySearch({
  query,
  onQuery,
}: {
  query: string
  onQuery: (query: string) => void
}) {
  return (
    <label className="library-search">
      <Search size={16} aria-hidden="true" />
      <span className="visually-hidden">Search agents</span>
      <input
        type="search"
        value={query}
        placeholder="Search by job or keyword"
        onChange={(event) => onQuery(event.target.value)}
      />
    </label>
  )
}

export function ClearFiltersButton({ onClear }: { onClear: () => void }) {
  return (
    <button type="button" className="library-clear" onClick={onClear}>
      Clear filters
    </button>
  )
}

function LibraryViewSwitch({
  viewMode,
  onChange,
}: {
  viewMode: LibraryViewMode
  onChange: (viewMode: LibraryViewMode) => void
}) {
  return (
    <div className="library-view-switch" role="group" aria-label="View">
      <button
        type="button"
        aria-pressed={viewMode === 'cards'}
        onClick={() => onChange('cards')}
      >
        Cards
      </button>
      <button
        type="button"
        aria-pressed={viewMode === 'list'}
        onClick={() => onChange('list')}
      >
        List
      </button>
    </div>
  )
}

export function LibraryResultsToolbar({
  shown,
  total,
  viewMode,
  onViewMode,
}: {
  shown: number
  total: number
  viewMode: LibraryViewMode
  onViewMode: (viewMode: LibraryViewMode) => void
}) {
  return (
    <div className="library-results-toolbar">
      <div className="library-results-head" aria-live="polite">
        <h2 id="library-results">
          {shown} {shown === 1 ? 'agent' : 'agents'}
        </h2>
        <span>of {total} in the library</span>
      </div>
      <LibraryViewSwitch viewMode={viewMode} onChange={onViewMode} />
    </div>
  )
}

export function LibraryEmpty({ onClear }: { onClear: () => void }) {
  return (
    <div className="library-empty">
      <p>No agents match these filters.</p>
      <button type="button" onClick={onClear}>
        Clear filters
      </button>
    </div>
  )
}
