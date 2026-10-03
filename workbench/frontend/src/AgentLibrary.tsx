import { useMemo, useState } from 'react'
import { CircleAlert, RefreshCw } from 'lucide-react'
import {
  facetKeys,
  filterTemplates,
  liveFacets,
  toggleFacet,
  type FacetKey,
  type Selection,
} from './library-catalog'
import type { LibraryCatalogState } from './library-catalog-client'
import type { LibraryTab, ReadyAgent } from './library-helpers'
import { LibraryBrowse } from './LibraryBrowse'
import { LibraryDetail } from './LibraryDetail'
import { LibraryLoading } from './LibraryLoading'
import { useScorecards } from './scorecards-client'
import { useLibraryViewMode } from './use-library-view-mode'
import type { Agent, CreationCapability } from './workspace-config'
import './library.css'

export type { ReadyAgent }

export function AgentLibrary({
  active,
  library,
  capability,
  readyAgentFor,
  previewFor,
  foundryPortal,
  busy,
  onCreate,
  onOpenCreate,
  onTest,
  onOpen,
}: {
  active: boolean
  library: LibraryCatalogState
  capability?: CreationCapability
  readyAgentFor: (templateId: string) => ReadyAgent | undefined
  previewFor: (templateId: string) => Agent | undefined
  foundryPortal?: string | null
  busy: boolean
  onCreate: (templateId: string) => void
  onOpenCreate?: () => void
  onTest: (agent: Agent, input: string) => void
  onOpen?: (label: string) => void
}) {
  const { catalog, error } = library
  const [query, setQuery] = useState('')
  const [selection, setSelection] = useState<Selection>({})
  const [openId, setOpenId] = useState('')
  const [tab, setTab] = useState<LibraryTab>('overview')
  const [notice, setNotice] = useState('')
  const [viewMode, setLibraryView] = useLibraryViewMode()

  const results = useMemo(
    () => (catalog ? filterTemplates(catalog, query, selection) : []),
    [catalog, query, selection],
  )
  const facets = useMemo(
    () => (catalog ? liveFacets(catalog, query, selection) : []),
    [catalog, query, selection],
  )
  const open = catalog?.templates.find((item) => item.id === openId)
  const scorecards = useScorecards(
    active && !!open && (tab === 'results' || tab === 'export'),
  )
  const previewsOn = !!catalog?.templates.some((item) => previewFor(item.id))
  const filtered = !!query.trim() || facetKeys.some((key) => selection[key])

  if (!active) return null

  function toggle(key: FacetKey, id: string) {
    setSelection((current) => toggleFacet(current, key, id))
  }

  function show(id: string) {
    setOpenId(id)
    setTab('overview')
    setNotice('')
    onOpen?.(catalog?.templates.find((item) => item.id === id)?.label ?? '')
    document.querySelector('.library-view')?.scrollTo({ top: 0 })
  }

  function clearFilters() {
    setQuery('')
    setSelection({})
  }

  return (
    <main className="secondary-view library-view">
      {error && (
        <div className="section-heading">
          <h1>Agent library</h1>
        </div>
      )}
      {error ? (
        <div className="library-error" role="alert">
          <CircleAlert size={18} />
          <p>{error}</p>
          <button type="button" onClick={library.retry}>
            <RefreshCw size={15} /> Retry
          </button>
        </div>
      ) : !catalog ? (
        <LibraryLoading />
      ) : open ? (
        <LibraryDetail
          template={open}
          tab={tab}
          scorecards={scorecards}
          capability={capability}
          foundryPortal={foundryPortal}
          ready={readyAgentFor(open.id)}
          preview={previewFor(open.id)}
          busy={busy}
          notice={notice}
          onTab={setTab}
          onBack={() => {
            setOpenId('')
            setNotice('')
            onOpen?.('')
          }}
          onCreate={() => onCreate(open.id)}
          onTest={onTest}
          onNotice={setNotice}
        />
      ) : (
        <LibraryBrowse
          catalog={catalog}
          results={results}
          facets={facets}
          query={query}
          selection={selection}
          filtered={filtered}
          viewMode={viewMode}
          previewsOn={previewsOn}
          busy={busy}
          readyAgentFor={readyAgentFor}
          previewFor={previewFor}
          onQuery={setQuery}
          onToggle={toggle}
          onClear={clearFilters}
          onViewMode={setLibraryView}
          onShow={show}
          onTest={onTest}
          onOpenCreate={onOpenCreate}
        />
      )}
    </main>
  )
}
