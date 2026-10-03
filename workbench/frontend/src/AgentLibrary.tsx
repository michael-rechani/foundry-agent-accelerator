import { useMemo, useState, type ReactNode } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  Check,
  CircleAlert,
  Construction,
  Copy,
  Download,
  FlaskConical,
  MessageSquare,
  PackageOpen,
  RefreshCw,
  Search,
  ShieldCheck,
  UserCheck,
  Wrench,
} from 'lucide-react'
import { creationRequest } from './agent-creation-client'
import { agentIcons, fallbackAgentIcon } from './agent-icons'
import { demoScenarios } from './demo-scenarios'
import { FoundryLink } from './FoundryLink'
import { foundryAgentUrl } from './foundry-links'
import {
  agentDefinition,
  definitionFileName,
  evaluationFileName,
  evaluationLines,
} from './foundry-handoff'
import {
  facetKeys,
  filterTemplates,
  liveFacets,
  toggleFacet,
  type FacetKey,
  type LibraryTemplate,
  type Selection,
} from './library-catalog'
import type { LibraryCatalogState } from './library-catalog-client'
import { FacetGroups, FacetMenus } from './LibraryFilters'
import { LibraryList } from './LibraryList'
import { ScorecardPanel } from './ScorecardPanel'
import { useScorecards, type ScorecardsState } from './scorecards-client'
import { tabKeyDown } from './tab-keys'
import type { Agent, CreationCapability } from './workspace-config'
import './library.css'

const tones: Record<string, string> = {
  reviewed: 'good',
  'tested-live': 'good',
  sample: 'caution',
  simulated: 'info',
  'connected-required': 'caution',
}
type Tab = 'overview' | 'test' | 'results' | 'export'
type LibraryViewMode = 'cards' | 'list'

export type ReadyAgent = { agent: Agent; recordId: string }

const libraryViewStorageKey = 'foundry-lab-library-view'

function readLibraryView(): LibraryViewMode {
  if (typeof window === 'undefined') return 'cards'
  try {
    return window.localStorage.getItem(libraryViewStorageKey) === 'list'
      ? 'list'
      : 'cards'
  } catch {
    return 'cards'
  }
}

function storesOpenChat(
  template: LibraryTemplate,
  preview?: Agent,
  ready?: ReadyAgent,
) {
  return template.tool_mode.id !== 'connected-required' && !!(preview || ready)
}

function runTemplateChat(
  template: LibraryTemplate,
  preview: Agent | undefined,
  ready: ReadyAgent | undefined,
  onTest: (agent: Agent, input: string) => void,
) {
  if (template.tool_mode.id === 'connected-required') return
  if (preview) onTest(preview, template.sample_input)
  else if (ready) onTest(ready.agent, template.sample_input)
}

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
  const [tab, setTab] = useState<Tab>('overview')
  const [notice, setNotice] = useState('')
  const [viewMode, setViewMode] = useState<LibraryViewMode>(readLibraryView)

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

  function setLibraryView(next: LibraryViewMode) {
    setViewMode(next)
    try {
      window.localStorage.setItem(libraryViewStorageKey, next)
    } catch {}
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
        <>
          <LibraryHero>
            <ol className="library-path" aria-label="How the library works">
              <li>
                <span>1</span>Pick an agent
              </li>
              <li>
                <span>2</span>
                {previewsOn ? (
                  'Try it in Chat'
                ) : (
                  <CreateStepLink onOpenCreate={onOpenCreate} />
                )}
              </li>
              <li>
                <span>3</span>
                {previewsOn ? (
                  <CreateStepLink onOpenCreate={onOpenCreate} />
                ) : (
                  'Try it with sample data'
                )}
              </li>
              <li>
                <span>4</span>Take it to Foundry
              </li>
            </ol>
          </LibraryHero>
          {viewMode === 'cards' ? (
            <div className="library-layout">
              <aside className="library-filters" aria-label="Library filters">
                <label className="library-search">
                  <Search size={16} aria-hidden="true" />
                  <span className="visually-hidden">Search agents</span>
                  <input
                    type="search"
                    value={query}
                    placeholder="Search by job or keyword"
                    onChange={(event) => setQuery(event.target.value)}
                  />
                </label>
                <FacetGroups
                  catalog={catalog}
                  facets={facets}
                  selection={selection}
                  onToggle={toggle}
                />
                {filtered && (
                  <button
                    type="button"
                    className="library-clear"
                    onClick={clearFilters}
                  >
                    Clear filters
                  </button>
                )}
              </aside>
              <div>
                {!filtered && (
                  <StartHere templates={catalog.templates} onOpen={show} />
                )}
                <section aria-labelledby="library-results">
                  <div className="library-results-toolbar">
                    <div className="library-results-head" aria-live="polite">
                      <h2 id="library-results">
                        {results.length}{' '}
                        {results.length === 1 ? 'agent' : 'agents'}
                      </h2>
                      <span>of {catalog.templates.length} in the library</span>
                    </div>
                    <LibraryViewSwitch
                      viewMode={viewMode}
                      onChange={setLibraryView}
                    />
                  </div>
                  {results.length ? (
                    <ul className="library-grid">
                      {results.map((item) => (
                        <li key={item.id}>
                          <LibraryCard
                            template={item}
                            ready={!!readyAgentFor(item.id)}
                            onOpen={() => show(item.id)}
                          />
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="library-empty">
                      <p>No agents match these filters.</p>
                      <button type="button" onClick={clearFilters}>
                        Clear filters
                      </button>
                    </div>
                  )}
                </section>
              </div>
            </div>
          ) : (
            <section
              className="library-list-shell"
              aria-labelledby="library-results"
            >
              <div
                className="library-filter-strip"
                aria-label="Library filters"
              >
                <label className="library-search">
                  <Search size={16} aria-hidden="true" />
                  <span className="visually-hidden">Search agents</span>
                  <input
                    type="search"
                    value={query}
                    placeholder="Search by job or keyword"
                    onChange={(event) => setQuery(event.target.value)}
                  />
                </label>
                <FacetMenus
                  catalog={catalog}
                  facets={facets}
                  selection={selection}
                  onToggle={toggle}
                />
                {filtered && (
                  <button
                    type="button"
                    className="library-clear"
                    onClick={clearFilters}
                  >
                    Clear filters
                  </button>
                )}
              </div>
              <div className="library-results-toolbar">
                <div className="library-results-head" aria-live="polite">
                  <h2 id="library-results">
                    {results.length} {results.length === 1 ? 'agent' : 'agents'}
                  </h2>
                  <span>of {catalog.templates.length} in the library</span>
                </div>
                <LibraryViewSwitch
                  viewMode={viewMode}
                  onChange={setLibraryView}
                />
              </div>
              {results.length ? (
                <LibraryList
                  templates={results}
                  onOpen={show}
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
                          : show(template.id),
                    }
                  }}
                />
              ) : (
                <div className="library-empty">
                  <p>No agents match these filters.</p>
                  <button type="button" onClick={clearFilters}>
                    Clear filters
                  </button>
                </div>
              )}
            </section>
          )}
        </>
      )}
    </main>
  )
}

function LibraryHero({ children }: { children: ReactNode }) {
  return (
    <header className="library-hero">
      <p className="library-eyebrow">Agent library</p>
      <h1>Find an agent for the job</h1>
      <p>
        Pick an agent, try it with sample inputs, see what it needs and what it
        leaves to a person, then take it to your Microsoft Foundry project.
      </p>
      {children}
    </header>
  )
}

function CreateStepLink({ onOpenCreate }: { onOpenCreate?: () => void }) {
  if (!onOpenCreate) return <>Make your own copy</>
  return (
    <button type="button" className="library-path-link" onClick={onOpenCreate}>
      Make your own copy
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

// Grey shapes in the same places as the real page, so nothing jumps when the
// agents arrive. They do not animate, which keeps a remote desktop quiet.
function LibraryLoading() {
  return (
    <>
      <p role="status" className="visually-hidden">
        Loading the agent library...
      </p>
      <LibraryHero>
        <ol className="library-path" aria-hidden="true">
          {[1, 2, 3, 4].map((step) => (
            <li key={step}>
              <span>{step}</span>
              <div className="library-bar library-bar-step" />
            </li>
          ))}
        </ol>
      </LibraryHero>
      <div className="library-layout" aria-hidden="true">
        <div className="library-filters">
          <div className="library-search">
            <Search size={16} />
            <div className="library-bar library-bar-search" />
          </div>
          {[3, 5, 2, 3].map((rows, group) => (
            <div key={group} className="library-placeholder-group">
              <div className="library-bar library-bar-legend" />
              {Array.from({ length: rows }, (_, row) => (
                <div key={row} className="library-bar library-bar-row" />
              ))}
            </div>
          ))}
        </div>
        <div>
          <section className="library-start">
            <div className="library-start-head">
              <h2 className="library-bar-count">&nbsp;</h2>
              <span>&nbsp;</span>
            </div>
            <ul className="library-start-list">
              {demoScenarios.map((scenario) => (
                <li key={scenario.id}>
                  <div className="library-start-placeholder">
                    <div className="library-bar library-bar-icon" />
                    <div className="library-bar library-bar-title" />
                    <div className="library-bar-text">
                      <div className="library-bar library-bar-line" />
                      <div className="library-bar library-bar-line" />
                      <div className="library-bar library-bar-line library-bar-short" />
                    </div>
                    <div className="library-bar library-bar-foot" />
                  </div>
                </li>
              ))}
            </ul>
          </section>
          <div className="library-results-toolbar" aria-hidden="true">
            <div className="library-results-head">
              <h2 className="library-bar-count">&nbsp;</h2>
              <span>&nbsp;</span>
            </div>
            <div className="library-bar library-bar-switch" />
          </div>
          <ul className="library-grid">
            {Array.from({ length: 6 }, (_, card) => (
              <li key={card}>
                <div className="library-placeholder">
                  <div className="library-bar library-bar-kicker" />
                  <div className="library-card-head">
                    <div className="library-bar library-bar-icon" />
                    <div className="library-bar library-bar-title" />
                  </div>
                  <div className="library-bar library-bar-line" />
                  <div className="library-bar library-bar-line" />
                  <div className="library-bar library-bar-line library-bar-short" />
                  <div className="library-bar library-bar-pills" />
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  )
}

function inProgress(template: LibraryTemplate) {
  return template.readiness.id === 'sample'
}

function ReadinessBadge({ template }: { template: LibraryTemplate }) {
  const Icon = inProgress(template) ? Construction : BadgeCheck
  return (
    <span
      className={`library-badge ${tones[template.readiness.id] || ''}`}
      title={template.readiness.description}
    >
      <Icon size={12} aria-hidden="true" />
      {template.readiness.label}
    </span>
  )
}

function Badges({ template }: { template: LibraryTemplate }) {
  return (
    <>
      <ReadinessBadge template={template} />
      <span className={`library-badge ${tones[template.tool_mode.id] || ''}`}>
        {template.tool_mode.label}
      </span>
    </>
  )
}

// The tile is decoration; the agent's name beside it says everything.
function AgentIcon({ id }: { id: string }) {
  const Icon = agentIcons[id] ?? fallbackAgentIcon
  return (
    <span className="library-card-icon" aria-hidden="true">
      <Icon size={20} strokeWidth={1.8} />
    </span>
  )
}

function LibraryCard({
  template,
  ready,
  onOpen,
}: {
  template: LibraryTemplate
  ready: boolean
  onOpen: () => void
}) {
  return (
    <button
      type="button"
      className="library-card"
      data-sector={template.sector.id}
      onClick={onOpen}
    >
      <span className="library-kicker">
        <span className="library-sector-dot" aria-hidden="true" />
        {template.sector.label} · {template.industry.label}
      </span>
      <span className="library-card-head">
        <AgentIcon id={template.id} />
        <strong>{template.label}</strong>
      </span>
      <span className="library-summary">{template.summary}</span>
      <span className="library-decides">
        <UserCheck size={13} aria-hidden="true" />
        {template.human_decision}
      </span>
      <span className="library-badges">
        <Badges template={template} />
        {ready && (
          <span className="library-badge good">
            <Check size={12} aria-hidden="true" /> Made in this Lab
          </span>
        )}
      </span>
    </button>
  )
}

// Three agents with a ready-made example, taken from the guided demos so the
// two never drift apart. A card opens the agent's page, where "Try it with an
// example" sits.
function StartHere({
  templates,
  onOpen,
}: {
  templates: LibraryTemplate[]
  onOpen: (templateId: string) => void
}) {
  const featured = demoScenarios.filter((scenario) =>
    templates.some((item) => item.id === scenario.templateId),
  )
  if (!featured.length) return null
  return (
    <section className="library-start" aria-labelledby="library-start">
      <div className="library-start-head">
        <h2 id="library-start">Start here</h2>
        <span>Open one to try it with an example.</span>
      </div>
      <ul className="library-start-list">
        {featured.map((scenario) => (
          <li key={scenario.id}>
            <button
              type="button"
              className="library-start-card"
              onClick={() => onOpen(scenario.templateId)}
            >
              <AgentIcon id={scenario.templateId} />
              <strong>{scenario.title}</strong>
              <span className="library-start-text">{scenario.description}</span>
              <span className="library-start-foot">
                <span>{scenario.templateLabel}</span>
                <ArrowRight size={16} aria-hidden="true" />
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

function saveFile(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  URL.revokeObjectURL(url)
}

function LibraryDetail({
  template,
  tab,
  scorecards,
  capability,
  foundryPortal,
  ready,
  preview,
  busy,
  notice,
  onTab,
  onBack,
  onCreate,
  onTest,
  onNotice,
}: {
  template: LibraryTemplate
  tab: Tab
  scorecards: ScorecardsState
  capability?: CreationCapability
  foundryPortal?: string | null
  ready?: ReadyAgent
  preview?: Agent
  busy: boolean
  notice: string
  onTab: (tab: Tab) => void
  onBack: () => void
  onCreate: () => void
  onTest: (agent: Agent, input: string) => void
  onNotice: (text: string) => void
}) {
  const tabs: [Tab, string][] = [
    ['overview', 'Overview'],
    ['test', 'Try it'],
    ['results', 'Test results'],
    ['export', 'Take it to Foundry'],
  ]
  const tabIds = tabs.map(([id]) => id)
  const runnable = template.tool_mode.id !== 'connected-required'
  const creationNote = !capability
    ? 'Agent creation is not available in this Lab.'
    : capability.enabled
      ? 'Creating prepares a setup for review. Publishing it requires an operator key and incurs Foundry charges.'
      : capability.reason === 'local_preview'
        ? 'Local preview: you can prepare and review a setup, but nothing is published.'
        : 'Publishing is not enabled here. You can still prepare and review a setup.'

  function tryIt() {
    if (opensChat) runTemplateChat(template, preview, ready, onTest)
    else onTab('test')
  }
  const opensChat = storesOpenChat(template, preview, ready)

  async function copySample() {
    try {
      await navigator.clipboard.writeText(template.sample_input)
      onNotice('Example input copied.')
    } catch {
      onNotice('Clipboard unavailable. Select and copy the example manually.')
    }
  }

  async function downloadRecord(id: string) {
    try {
      const record = await creationRequest(`agents/${id}`)
      saveFile(
        `${template.id}-record.json`,
        JSON.stringify(record, null, 2),
        'application/json',
      )
      onNotice('Saved record downloaded. Use it with the export command below.')
    } catch (problem) {
      onNotice(
        problem instanceof Error
          ? problem.message
          : 'The saved record could not be downloaded.',
      )
    }
  }

  const testCases = scorecards.scorecards?.scorecards.find(
    (card) => card.template_id === template.id,
  )?.cases

  function downloadDefinition() {
    saveFile(
      definitionFileName(template.id),
      JSON.stringify(agentDefinition(template), null, 2) + '\n',
      'application/json',
    )
    onNotice('Agent definition downloaded.')
  }

  function downloadTestCases() {
    if (!testCases) return
    saveFile(
      evaluationFileName(template.id),
      evaluationLines(testCases),
      'application/x-ndjson',
    )
    onNotice('Test requests downloaded.')
  }

  return (
    <article className="library-detail" aria-labelledby="library-detail-title">
      <button type="button" className="library-back" onClick={onBack}>
        <ArrowLeft size={16} /> Back to all agents
      </button>
      <div className="library-badges">
        <span className="library-badge">{template.industry.label}</span>
        <Badges template={template} />
        <span className="library-badge hood-only">{template.sector.label}</span>
        {template.tasks.map((task) => (
          <span key={task.id} className="library-badge hood-only">
            {task.label}
          </span>
        ))}
      </div>
      <h1 id="library-detail-title">{template.label}</h1>
      <p className="library-lede">{template.summary}</p>
      <div className="library-actions library-hero-actions">
        <button
          type="button"
          className="library-primary"
          disabled={busy}
          onClick={tryIt}
        >
          <MessageSquare size={16} />{' '}
          {opensChat ? 'Try it in Chat' : 'Try it with an example'}
        </button>
        <button
          type="button"
          className="library-secondary"
          onClick={() => onTab('export')}
        >
          Take it to Foundry <ArrowRight size={16} />
        </button>
      </div>
      {inProgress(template) && (
        <div className="library-progress" role="note">
          <Construction size={18} aria-hidden="true" />
          <p>
            <strong>In progress. </strong>A person hasn&apos;t signed off on its
            test answers yet. Try it with sample data; answers may change.
          </p>
        </div>
      )}
      <div className="library-decision" role="note">
        <UserCheck size={18} aria-hidden="true" />
        <p>
          <strong>A person decides. </strong>
          {template.human_decision}
        </p>
      </div>
      <div className="library-tabs" role="tablist" aria-label="Agent details">
        {tabs.map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`library-tab-${id}`}
            aria-selected={tab === id}
            aria-controls="library-tabpanel"
            tabIndex={tab === id ? 0 : -1}
            onClick={() => onTab(id)}
            onKeyDown={(event) => tabKeyDown(event, tabIds, id, onTab)}
          >
            {label}
          </button>
        ))}
      </div>
      {notice && (
        <p className="library-notice" role="status">
          {notice}
        </p>
      )}
      <div
        className="library-tabpanel"
        id="library-tabpanel"
        role="tabpanel"
        aria-labelledby={`library-tab-${tab}`}
      >
        {tab === 'overview' && (
          <>
            <dl className="library-facts">
              <div>
                <dt>
                  <ShieldCheck size={15} aria-hidden="true" /> Readiness
                </dt>
                <dd>
                  <strong>{template.readiness.label}</strong>
                  <span>{template.readiness.description}</span>
                </dd>
              </div>
              <div>
                <dt>
                  <Wrench size={15} aria-hidden="true" /> Tools
                </dt>
                <dd>
                  <strong>{template.tool_mode.label}</strong>
                  <span>{template.tool_mode.description}</span>
                </dd>
              </div>
              <div className="hood-only">
                <dt>
                  <FlaskConical size={15} aria-hidden="true" /> Model profile
                </dt>
                <dd>
                  <strong>{template.model_profile.label}</strong>
                  <span>
                    Relative cost {template.runtime_hint.relative_cost}, latency{' '}
                    {template.runtime_hint.relative_latency}.{' '}
                    {template.runtime_hint.basis}
                  </span>
                </dd>
              </div>
              <div className="hood-only">
                <dt>
                  <PackageOpen size={15} aria-hidden="true" /> Export
                </dt>
                <dd>
                  <strong>
                    {template.export.exportable
                      ? 'After creation'
                      : 'Not available'}
                  </strong>
                  <span>{template.export.package_format}</span>
                </dd>
              </div>
            </dl>
            <div className="library-columns">
              <section className="library-panel">
                <h2>What you give it</h2>
                <p>{template.input}</p>
                <h2>What you get back</h2>
                <p>{template.output}</p>
                <h2>What a good answer does</h2>
                <p>{template.expected_behavior}</p>
                <p className="library-muted">
                  Based on its acceptance tests, not a recorded answer.
                </p>
              </section>
              <section className="library-panel">
                <h2>What it won&apos;t do</h2>
                <p>{template.limits}</p>
                {template.tools.length > 0 && (
                  <>
                    <h2>Sample lookups it uses</h2>
                    <ul className="library-tools">
                      {template.tools.map((tool) => (
                        <li key={tool.name}>
                          {tool.description}
                          <code className="hood-only">{tool.name}</code>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                <div className="hood-only">
                  <h2>Before you use it</h2>
                  <ul>
                    {template.prerequisites.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              </section>
            </div>
          </>
        )}
        {tab === 'test' && (
          <div className="library-columns">
            <section className="library-panel">
              <h2>Example to try</h2>
              <pre className="library-sample">{template.sample_input}</pre>
              <div className="library-actions">
                {!runnable ? (
                  <p className="library-muted">
                    This agent needs a connection to your own system and cannot
                    run in the Lab.
                  </p>
                ) : preview ? (
                  <button
                    type="button"
                    className="library-primary"
                    disabled={busy}
                    onClick={() => onTest(preview, template.sample_input)}
                  >
                    <MessageSquare size={16} /> Try it in Chat
                  </button>
                ) : null}
                {runnable && ready ? (
                  <button
                    type="button"
                    className={
                      preview ? 'library-secondary' : 'library-primary'
                    }
                    disabled={busy}
                    onClick={() => onTest(ready.agent, template.sample_input)}
                  >
                    Open your created agent <ArrowRight size={16} />
                  </button>
                ) : runnable && !preview ? (
                  <button
                    type="button"
                    className="library-primary"
                    disabled={!capability || busy}
                    onClick={onCreate}
                  >
                    Create this agent to test it <ArrowRight size={16} />
                  </button>
                ) : null}
                <button
                  type="button"
                  className="library-secondary"
                  onClick={() => void copySample()}
                >
                  <Copy size={15} /> Copy example
                </button>
              </div>
              <p className="library-muted">
                {preview
                  ? 'Opens Chat with this example ready to send. Nothing happens until you press Send, which calls the model and has a small cost. Preview chats aren\u2019t saved.'
                  : ready
                    ? `Uses ${ready.agent.label}. Opens Chat with this example ready to send. Nothing happens until you press Send, which calls the model and has a small cost.`
                    : creationNote}
              </p>
              {preview && (
                <p className="library-muted hood-only">
                  A preview calls the model directly rather than running as a
                  hosted agent, so test the created agent before handing it to a
                  customer.
                </p>
              )}
            </section>
            <section className="library-panel">
              <h2>What to look for in the answer</h2>
              <ul className="library-checks">
                <li>{template.expected_behavior}</li>
                <li>It stays within its limits. {template.limits}</li>
                <li>It leaves the decision to a person.</li>
              </ul>
              <p className="library-muted">
                {preview
                  ? 'Use sample data only. Preview chats are not saved; create the agent to save or share conversations.'
                  : 'Use sample data only. Chat responses are not saved unless you choose Save to shared history.'}
              </p>
            </section>
          </div>
        )}
        {tab === 'results' && (
          <ScorecardPanel templateId={template.id} state={scorecards} />
        )}
        {tab === 'export' && (
          <div className="library-columns">
            <div className="library-stack">
              <section className="library-panel">
                <h2>Start in your Foundry project</h2>
                <p>
                  Download the setup and the test requests, then use them in a
                  Foundry project you control. Nothing is created until you do.
                </p>
                <div className="library-download">
                  <button
                    type="button"
                    className="library-secondary"
                    onClick={downloadDefinition}
                  >
                    <Download size={16} /> Download agent definition
                  </button>
                  <p className="library-muted">
                    Instructions and settings for a Foundry prompt agent. Add
                    your own model deployment.
                  </p>
                </div>
                <div className="library-download">
                  {testCases ? (
                    <>
                      <button
                        type="button"
                        className="library-secondary"
                        onClick={downloadTestCases}
                      >
                        <Download size={16} /> Download test requests
                      </button>
                      <p className="library-muted">
                        {testCases.length} requests for a Foundry evaluation,
                        each with what a good answer shows.
                      </p>
                    </>
                  ) : scorecards.error ? (
                    <>
                      <p className="library-muted">
                        The test requests did not load.
                      </p>
                      <button
                        type="button"
                        className="library-secondary"
                        onClick={scorecards.retry}
                      >
                        <RefreshCw size={14} /> Try again
                      </button>
                    </>
                  ) : scorecards.scorecards ? (
                    <p className="library-muted">
                      This agent has no test requests yet.
                    </p>
                  ) : (
                    <p className="library-muted" role="status">
                      Checking for test requests...
                    </p>
                  )}
                </div>
              </section>
              <section className="library-panel">
                <h2>Or get the full hosted-agent package</h2>
                <p>{template.export.description}</p>
                <p className="library-muted hood-only">
                  Format {template.export.package_format}. Target: a Microsoft
                  Foundry hosted agent in a project you control.
                </p>
                {!template.export.exportable ? (
                  <p className="library-muted">
                    Export is not available for this agent yet.
                  </p>
                ) : ready ? (
                  <button
                    type="button"
                    className="library-primary"
                    onClick={() => void downloadRecord(ready.recordId)}
                  >
                    <Download size={16} /> Download saved record
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      className="library-primary"
                      disabled={!capability || busy}
                      onClick={onCreate}
                    >
                      Create this agent to get the package{' '}
                      <ArrowRight size={16} />
                    </button>
                    <p className="library-muted">
                      {capability
                        ? 'Opens Create agent with this template. Nothing is created until you confirm on the last step.'
                        : creationNote}
                    </p>
                  </>
                )}
                {ready && foundryPortal && (
                  <p className="library-muted hood-only">
                    <FoundryLink
                      href={foundryAgentUrl(foundryPortal, ready.agent.agent)}
                    >
                      Open this agent in Foundry
                    </FoundryLink>
                  </p>
                )}
              </section>
            </div>
            <section className="library-panel">
              <h2>Set it up in your Foundry project</h2>
              <ol className="library-steps">
                <li>Provide a model deployment in your own Foundry project.</li>
                <li>
                  Create a prompt agent from the definition file, or paste its
                  instructions into the agent builder.
                </li>
                <li>
                  Review the instructions, limits and acceptance cases with your
                  policy owners.
                </li>
                {template.tool_mode.id !== 'none' && (
                  <li>
                    Replace the sample lookups with reviewed connectors to your
                    own systems.
                  </li>
                )}
                {testCases && (
                  <li>
                    Run the test requests as a Foundry evaluation and read each
                    answer against what a good answer shows.
                  </li>
                )}
                <li className="hood-only">
                  Build and check the bundle from the saved record:
                </li>
              </ol>
              <pre className="library-sample library-command hood-only">
                {`python hosted-agents/bundle.py export-created --record ${template.id}-record.json --output ${template.id}.agent-bundle.zip
python hosted-agents/bundle.py inspect ${template.id}.agent-bundle.zip
python hosted-agents/bundle.py deploy ${template.id}.agent-bundle.zip --endpoint <your-project-endpoint> --model <your-deployment> --agent-name <your-agent-name>`}
              </pre>
              <p className="library-muted">
                There is no one-click cross-environment deployment. Deploying
                creates a billable hosted version in your project; your team
                runs it with its own credentials.
              </p>
            </section>
          </div>
        )}
      </div>
    </article>
  )
}
