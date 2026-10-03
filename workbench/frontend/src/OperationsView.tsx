import { useMemo } from 'react'
import { ArrowRight, Bot, Coins, HeartPulse, ScrollText } from 'lucide-react'
import { FoundryLink } from './FoundryLink'
import {
  type DependencyHealthSnapshot,
  type DependencyStatus,
} from './dependency-health'
import type { Measurement } from './performance-stats'
import {
  estimateCost,
  formatTokens,
  loadRates,
  totalUsage,
  usageLabel,
} from './token-usage'
import './operations.css'

const outcomeLabels: Record<Measurement['outcome'], string> = {
  completed: 'Completed',
  failed: 'Failed',
  stopped: 'Stopped',
  'timed-out': 'Timed out',
}

const seconds = (value: number) => `${(value / 1000).toFixed(1)}s`

function checkedAtLabel(value: number) {
  return new Date(value).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function serviceLabel(status: DependencyStatus) {
  switch (status) {
    case 'ready':
      return 'Ready'
    case 'degraded':
      return 'Needs attention'
    case 'starting':
      return 'Starting'
    case 'disabled':
      return 'Off'
    default:
      return "Couldn't check"
  }
}

function statusTone(status: DependencyStatus | 'failed') {
  switch (status) {
    case 'ready':
      return 'ready'
    case 'starting':
      return 'starting'
    case 'disabled':
      return 'off'
    case 'degraded':
      return 'attention'
    default:
      return 'failed'
  }
}

function overallLabel(health: DependencyHealthSnapshot | null) {
  if (!health || (health.loading && !health.data && !health.error))
    return 'Checking...'
  if (health.error) return "Couldn't check"
  switch (health.data?.status) {
    case 'ready':
      return 'Ready'
    case 'starting':
      return 'Starting'
    case 'disabled':
      return 'Preview only'
    default:
      return 'Needs attention'
  }
}

export function OperationsView({
  measurements,
  sampleCount,
  readyCount,
  createdCount,
  foundryPortal,
  health,
  onRefreshHealth,
  onLog,
}: {
  measurements: Measurement[]
  sampleCount?: number
  readyCount: number
  createdCount: number
  foundryPortal?: string | null
  health: DependencyHealthSnapshot | null
  onRefreshHealth: () => void
  onLog: () => void
}) {
  const totals = useMemo(
    () => totalUsage(measurements.map((item) => item.usage ?? null)),
    [measurements],
  )
  const rates = loadRates()
  const recent = [...measurements].reverse().slice(0, 5)
  const checkingServices =
    !health ||
    (health.loading && !health.checkedAt && !health.data && !health.error)
  const outcomes = {
    completed: measurements.filter((item) => item.outcome === 'completed')
      .length,
    failed: measurements.filter((item) => item.outcome === 'failed').length,
    stopped: measurements.filter((item) => item.outcome === 'stopped').length,
    'timed-out': measurements.filter((item) => item.outcome === 'timed-out')
      .length,
  }
  const services = [
    {
      name: 'Lab',
      status: 'ready' as const,
      label: 'Ready',
      detail: 'This page loaded, so the Lab is reachable.',
    },
    {
      name: 'Foundry connection',
      status: checkingServices
        ? ('unknown' as const)
        : health?.error
          ? ('unknown' as const)
          : (health?.data?.foundry ?? 'unknown'),
      label: checkingServices
        ? 'Checking...'
        : health?.error
          ? "Couldn't check"
          : serviceLabel(health?.data?.foundry ?? 'unknown'),
      detail: 'Used to run agents and open the project in Foundry.',
    },
    {
      name: 'History store',
      status: checkingServices
        ? ('unknown' as const)
        : health?.error
          ? ('unknown' as const)
          : (health?.data?.cosmos ?? 'unknown'),
      label: checkingServices
        ? 'Checking...'
        : health?.error
          ? "Couldn't check"
          : serviceLabel(health?.data?.cosmos ?? 'unknown'),
      detail: 'Used for saved shared chat history in this Lab.',
    },
  ]

  return (
    <main className="secondary-view operations-view">
      <div className="section-heading">
        <h1>Operations</h1>
        <p>
          Is the Lab healthy, what has it done in this browser tab, and where to
          find the full picture in Foundry.
        </p>
      </div>

      <div className="metric-strip metric-strip-4">
        <div>
          <HeartPulse size={18} />
          <span>Lab status</span>
          <strong>{overallLabel(health)}</strong>
          <small>
            {health?.checkedAt
              ? `Status as of ${checkedAtLabel(health.checkedAt)}`
              : 'Checking the live setup now.'}
          </small>
        </div>
        <div>
          <Bot size={18} />
          <span>Agents</span>
          <strong>
            {sampleCount === undefined
              ? 'Samples loading...'
              : `${sampleCount} samples`}
          </strong>
          <small>
            {readyCount} ready to chat, {createdCount} made here
          </small>
        </div>
        <div>
          <ScrollText size={18} />
          <span>Requests this tab</span>
          <strong>{measurements.length}</strong>
          <small>
            {outcomes.completed} completed, {outcomes.failed} failed,{' '}
            {outcomes.stopped} stopped, {outcomes['timed-out']} timed out
          </small>
        </div>
        <div>
          <Coins size={18} />
          <span>Tokens this tab</span>
          <strong>{formatTokens(totals.total)}</strong>
          <small>
            {rates
              ? `Estimated at your rates: ${estimateCost(
                  totals,
                  rates,
                ).toLocaleString('en-US', {
                  maximumFractionDigits: 4,
                })}`
              : 'Add your prices on the Performance page to see an estimate'}
          </small>
        </div>
      </div>

      <section
        className="operations-section"
        aria-labelledby="services-heading"
      >
        <div className="operations-heading-row">
          <h2 className="request-heading" id="services-heading">
            Services
          </h2>
          <div className="operations-actions">
            <span className="micro-label">
              {health?.checkedAt
                ? `Status as of ${checkedAtLabel(health.checkedAt)}`
                : 'Checking...'}
            </span>
            <button
              type="button"
              className="inline-link"
              onClick={onRefreshHealth}
              disabled={health?.loading === true}
            >
              {health?.loading ? 'Refreshing...' : 'Refresh'}
            </button>
          </div>
        </div>
        <p className="table-note">
          The Lab re-checks itself every minute, so this can be up to a minute
          behind.
        </p>
        <div className="request-table-wrap">
          <table className="request-table operations-services">
            <thead>
              <tr>
                <th scope="col">Service</th>
                <th scope="col">Status</th>
                <th scope="col">What it means</th>
              </tr>
            </thead>
            <tbody>
              {services.map((service) => (
                <tr key={service.name}>
                  <th scope="row">{service.name}</th>
                  <td>
                    <span
                      className={`operations-status ${statusTone(service.status)}`}
                    >
                      {service.label}
                    </span>
                  </td>
                  <td>{service.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="operations-columns">
        <section
          className="operations-section"
          aria-labelledby="recent-requests-heading"
        >
          <div className="operations-heading-row">
            <h2 className="request-heading" id="recent-requests-heading">
              Recent requests
            </h2>
            <button type="button" className="inline-link" onClick={onLog}>
              View all <ArrowRight size={14} aria-hidden="true" />
            </button>
          </div>
          {recent.length ? (
            <>
              <div className="request-table-wrap">
                <table
                  className="request-table"
                  aria-labelledby="recent-requests-heading"
                >
                  <thead>
                    <tr>
                      <th scope="col">Time</th>
                      <th scope="col">Agent</th>
                      <th scope="col">Outcome</th>
                      <th scope="col">Elapsed</th>
                      <th scope="col">Tokens</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recent.map((item) => (
                      <tr key={item.id}>
                        <td>
                          <time dateTime={new Date(item.at).toISOString()}>
                            {new Date(item.at).toLocaleTimeString()}
                          </time>
                        </td>
                        <td>{item.agent}</td>
                        <td>{outcomeLabels[item.outcome]}</td>
                        <td>{seconds(item.duration)}</td>
                        <td>
                          {item.outcome === 'completed'
                            ? (usageLabel(item.usage ?? null) ?? '—')
                            : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="table-note">
                Counts and requests reset when this browser tab reloads.
              </p>
            </>
          ) : (
            <p className="table-note operations-empty">
              No requests yet in this browser tab. Send a message in Chat and it
              appears here.
            </p>
          )}
        </section>

        <section
          className="operations-panel"
          aria-labelledby="foundry-deeper-heading"
        >
          <h2 className="request-heading" id="foundry-deeper-heading">
            Go deeper in Foundry
          </h2>
          <p>
            This page only sees this browser tab. For every user and session,
            use Foundry:
          </p>
          <ul>
            <li>
              <strong>Monitoring</strong>
              <span>Token use, response time and success rate</span>
            </li>
            <li>
              <strong>Tracing</strong>
              <span>A step-by-step view of one request</span>
            </li>
            <li>
              <strong>Evaluations</strong>
              <span>Quality and safety checks</span>
            </li>
            <li>
              <strong>Alerts</strong>
              <span>Be told when something slips</span>
            </li>
          </ul>
          <p className="table-note">
            Some of these need Application Insights connected to the project.
          </p>
          {foundryPortal && (
            <p className="foundry-note">
              For the full picture,{' '}
              <FoundryLink href={foundryPortal}>
                open the project in Foundry
              </FoundryLink>
              .
            </p>
          )}
        </section>
      </div>
    </main>
  )
}
