import type { ReactNode } from 'react'
import type {
  FacetKey,
  LibraryCatalog,
  LibraryTemplate,
  LiveFacet,
  Selection,
} from './library-catalog'
import {
  runTemplateChat,
  storesOpenChat,
  type LibraryViewMode,
  type ReadyAgent,
} from './library-helpers'
import { LibraryCard, StartHere } from './LibraryCards'
import {
  ClearFiltersButton,
  LibraryEmpty,
  LibraryResultsToolbar,
  LibrarySearch,
} from './LibraryControls'
import { FacetGroups, FacetMenus } from './LibraryFilters'
import { LibraryHero, LibraryPath } from './LibraryHero'
import { LibraryList } from './LibraryList'
import type { Agent } from './workspace-config'

// The landing page of the library: how it works, the filters and the agents,
// as cards or as a list.
export function LibraryBrowse({
  catalog,
  results,
  facets,
  query,
  selection,
  filtered,
  viewMode,
  previewsOn,
  busy,
  readyAgentFor,
  previewFor,
  onQuery,
  onToggle,
  onClear,
  onViewMode,
  onShow,
  onTest,
  onOpenCreate,
  onDemos,
  finder,
}: {
  catalog: LibraryCatalog
  results: LibraryTemplate[]
  facets: LiveFacet[]
  query: string
  selection: Selection
  filtered: boolean
  viewMode: LibraryViewMode
  previewsOn: boolean
  busy: boolean
  readyAgentFor: (templateId: string) => ReadyAgent | undefined
  previewFor: (templateId: string) => Agent | undefined
  onQuery: (query: string) => void
  onToggle: (key: FacetKey, id: string) => void
  onClear: () => void
  onViewMode: (viewMode: LibraryViewMode) => void
  onShow: (templateId: string) => void
  onTest: (agent: Agent, input: string) => void
  onOpenCreate?: () => void
  onDemos?: () => void
  finder?: ReactNode
}) {
  const toolbar = (
    <LibraryResultsToolbar
      shown={results.length}
      total={catalog.templates.length}
      viewMode={viewMode}
      onViewMode={onViewMode}
    />
  )
  return (
    <>
      <LibraryHero onDemos={onDemos}>
        {finder}
        <LibraryPath previewsOn={previewsOn} onOpenCreate={onOpenCreate} />
      </LibraryHero>
      {viewMode === 'cards' ? (
        <div className="library-layout">
          <aside className="library-filters" aria-label="Library filters">
            <LibrarySearch query={query} onQuery={onQuery} />
            <FacetGroups
              catalog={catalog}
              facets={facets}
              selection={selection}
              onToggle={onToggle}
            />
            {filtered && <ClearFiltersButton onClear={onClear} />}
          </aside>
          <div>
            {!filtered && (
              <StartHere templates={catalog.templates} onOpen={onShow} />
            )}
            <section aria-labelledby="library-results">
              {toolbar}
              {results.length ? (
                <ul className="library-grid">
                  {results.map((item) => (
                    <li key={item.id}>
                      <LibraryCard
                        template={item}
                        ready={!!readyAgentFor(item.id)}
                        onOpen={() => onShow(item.id)}
                      />
                    </li>
                  ))}
                </ul>
              ) : (
                <LibraryEmpty onClear={onClear} />
              )}
            </section>
          </div>
        </div>
      ) : (
        <section
          className="library-list-shell"
          aria-labelledby="library-results"
        >
          <div className="library-filter-strip" aria-label="Library filters">
            <LibrarySearch query={query} onQuery={onQuery} />
            <FacetMenus
              catalog={catalog}
              facets={facets}
              selection={selection}
              onToggle={onToggle}
            />
            {filtered && <ClearFiltersButton onClear={onClear} />}
          </div>
          {toolbar}
          {results.length ? (
            <LibraryList
              templates={results}
              onOpen={onShow}
              actionFor={(template) => {
                const preview = previewFor(template.id)
                const ready = readyAgentFor(template.id)
                const opensChat = storesOpenChat(template, preview, ready)
                return {
                  disabled: opensChat && busy,
                  label: opensChat ? 'Try in Chat' : 'Open',
                  onClick: () =>
                    opensChat
                      ? runTemplateChat(template, preview, ready, onTest)
                      : onShow(template.id),
                }
              }}
            />
          ) : (
            <LibraryEmpty onClear={onClear} />
          )}
        </section>
      )}
    </>
  )
}
