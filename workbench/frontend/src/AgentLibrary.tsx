import { useMemo, useState } from 'react'
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
import {
  facetKeys,
  filterTemplates,
  liveFacets,
  type FacetKey,
  type LibraryTemplate,
  type Selection,
} from './library-catalog'
import type { LibraryCatalogState } from './library-catalog-client'
import { ScorecardPanel } from './ScorecardPanel'
import { useScorecards, type ScorecardsState } from './scorecards-client'
import type { Agent, CreationCapability } from './workspace-config'
import './library.css'

const facetLabels: Record<FacetKey, string> = {
  sectors: 'Sector',
  industries: 'Industry',
  tasks: 'Task',
  readiness: 'Readiness',
  tool_modes: 'Works with',
}
const tones: Record<string, string> = {
  reviewed: 'good',
  'tested-live': 'good',
  sample: 'caution',
  simulated: 'info',
  'connected-required': 'caution',
}
type Tab = 'overview' | 'test' | 'results' | 'export'

export type ReadyAgent = { agent: Agent; recordId: string }

export function AgentLibrary({
  active,
  library,
  capability,
  readyAgentFor,
  previewFor,
  busy,
  onCreate,
  onTest,
  onOpen,
}: {
  active: boolean
  library: LibraryCatalogState
  capability?: CreationCapability
  readyAgentFor: (templateId: string) => ReadyAgent | undefined
  previewFor: (templateId: string) => Agent | undefined
  busy: boolean
  onCreate: (templateId: string) => void
  onTest: (agent: Agent, input: string) => void
  onOpen?: (label: string) => void
}) {
  const { catalog, error } = library
  const [query, setQuery] = useState('')
  const [selection, setSelection] = useState<Selection>({})
  const [openId, setOpenId] = useState('')
  const [tab, setTab] = useState<Tab>('overview')
  const [notice, setNotice] = useState('')

  const results = useMemo(
    () => (catalog ? filterTemplates(catalog, query, selection) : []),
    [catalog, query, selection],
  )
  const facets = useMemo(
    () => (catalog ? liveFacets(catalog, query, selection) : []),
    [catalog, query, selection],
  )
  const open = catalog?.templates.find((item) => item.id === openId)
  const scorecards = useScorecards(active && !!open && tab === 'results')
  const previewsOn = !!catalog?.templates.some((item) => previewFor(item.id))
  const filtered = !!query.trim() || facetKeys.some((key) => selection[key])

  if (!active) return null

  function toggle(key: FacetKey, id: string) {
    setSelection((current) => ({
      ...current,
      [key]: current[key] === id ? undefined : id,
    }))
  }

  function show(id: string) {
    setOpenId(id)
    setTab('overview')
    setNotice('')
    onOpen?.(catalog?.templates.find((item) => item.id === id)?.label ?? '')
    document.querySelector('.library-view')?.scrollTo({ top: 0 })
  }

  return (
    <main className="secondary-view library-view">
      {(error || !catalog) && (
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
        <p role="status">Loading the agent library...</p>
      ) : open ? (
        <LibraryDetail
          template={open}
          tab={tab}
          scorecards={scorecards}
          capability={capability}
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
          <header className="library-hero">
            <p className="library-eyebrow">Agent library</p>
            <h1>Find an agent for the job</h1>
            <p>
              Each agent does one job. Try it with sample inputs, see what it
              needs and what it leaves to a person, then take it to your own
              Microsoft Foundry project.
            </p>
            <ol className="library-path" aria-label="How the library works">
              <li>
                <span>1</span>Pick an agent
              </li>
              <li>
                <span>2</span>
                {previewsOn ? 'Try it in Chat' : 'Make your own copy'}
              </li>
              <li>
                <span>3</span>
                {previewsOn ? 'Make your own copy' : 'Try it with sample data'}
              </li>
              <li>
                <span>4</span>Take it to Foundry
              </li>
            </ol>
          </header>
          <div className="library-layout">
            <aside className="library-filters" aria-label="Library filters">
              <label className="library-search">
                <Search size={16} aria-hidden="true" />
                <span className="visually-hidden">Search agents</span>
                <input
                  type="search"
                  value={query}
                  placeholder="Search by job, team or keyword"
                  onChange={(event) => setQuery(event.target.value)}
                />
              </label>
              {facets.map((group) => (
                <fieldset key={group.key}>
                  <legend>{facetLabels[group.key]}</legend>
                  {group.items.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className="library-facet"
                      aria-pressed={selection[group.key] === item.id}
                      data-empty={item.count ? undefined : 'true'}
                      onClick={() => toggle(group.key, item.id)}
                    >
                      <span>{item.label}</span>
                      <small aria-label={`${item.count} agents`}>
                        {item.count}
                      </small>
                    </button>
                  ))}
                </fieldset>
              ))}
              {filtered && (
                <button
                  type="button"
                  className="library-clear"
                  onClick={() => {
                    setQuery('')
                    setSelection({})
                  }}
                >
                  Clear filters
                </button>
              )}
            </aside>
            <section aria-labelledby="library-results">
              <div className="library-results-head" aria-live="polite">
                <h2 id="library-results">
                  {results.length} {results.length === 1 ? 'agent' : 'agents'}
                </h2>
                <span>of {catalog.templates.length} in the library</span>
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
                  <button
                    type="button"
                    onClick={() => {
                      setQuery('')
                      setSelection({})
                    }}
                  >
                    Clear filters
                  </button>
                </div>
              )}
            </section>
          </div>
        </>
      )}
    </main>
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
      <strong>{template.label}</strong>
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

function LibraryDetail({
  template,
  tab,
  scorecards,
  capability,
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
  const runnable = template.tool_mode.id !== 'connected-required'
  const creationNote = !capability
    ? 'Agent creation is not available in this Lab.'
    : capability.enabled
      ? 'Creating prepares a setup for review. Publishing it requires an operator key and incurs Foundry charges.'
      : capability.reason === 'local_preview'
        ? 'Local preview: you can prepare and review a setup, but nothing is published.'
        : 'Publishing is not enabled here. You can still prepare and review a setup.'

  function tryIt() {
    if (runnable && preview) onTest(preview, template.sample_input)
    else if (runnable && ready) onTest(ready.agent, template.sample_input)
    else onTab('test')
  }

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
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(record, null, 2)], {
          type: 'application/json',
        }),
      )
      const link = document.createElement('a')
      link.href = url
      link.download = `${template.id}-record.json`
      link.click()
      URL.revokeObjectURL(url)
      onNotice('Saved record downloaded. Use it with the export command below.')
    } catch (problem) {
      onNotice(
        problem instanceof Error
          ? problem.message
          : 'The saved record could not be downloaded.',
      )
    }
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
          <MessageSquare size={16} /> Try it with an example
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
            onClick={() => onTab(id)}
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
                    <MessageSquare size={16} /> Try it now in Chat
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
            <section className="library-panel">
              <h2>Get the package</h2>
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
                <button
                  type="button"
                  className="library-primary"
                  disabled={!capability || busy}
                  onClick={onCreate}
                >
                  Create this agent first <ArrowRight size={16} />
                </button>
              )}
            </section>
            <section className="library-panel">
              <h2>Set it up in your Foundry project</h2>
              <ol className="library-steps">
                <li>Provide a model deployment in your own Foundry project.</li>
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
