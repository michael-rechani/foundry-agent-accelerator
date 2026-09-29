import {
  Activity,
  CircleAlert,
  Clock3,
  Gauge,
  MessageSquare,
} from 'lucide-react'

import { percentile, type Measurement } from './performance-stats'
import { FoundryLink } from './FoundryLink'
import { TokenCost } from './TokenCost'

const seconds = (value: number) => `${(value / 1000).toFixed(1)}s`

export function PerformanceView({
  measurements,
  preview,
  budgetAlerts = false,
  foundryPortal,
  onLog,
}: {
  measurements: Measurement[]
  preview: boolean
  budgetAlerts?: boolean
  foundryPortal?: string | null
  onLog: () => void
}) {
  const completed = measurements.filter((item) => item.outcome === 'completed')
  const average = completed.length
    ? completed.reduce((total, item) => total + item.duration, 0) /
      completed.length
    : null
  const p90 = percentile(
    completed.map((item) => item.duration),
    0.9,
  )
  return (
    <main className="secondary-view">
      <div className="section-heading">
        <h1>Performance</h1>
        <p>
          Response times measured in this browser tab for live requests. They
          include network and queueing time, reset when the page reloads, and
          are not a load test or a quality score.
        </p>
      </div>
      {foundryPortal && (
        <p className="foundry-note">
          For monitoring across every session and user,{' '}
          <FoundryLink href={foundryPortal}>
            open the project in Foundry
          </FoundryLink>
          .
        </p>
      )}
      <div className="metric-strip metric-strip-4">
        <div>
          <MessageSquare size={18} />
          <span>Completed</span>
          <strong>{completed.length}</strong>
        </div>
        <div>
          <Clock3 size={18} />
          <span>Average response</span>
          <strong>
            {average === null ? 'Not available' : seconds(average)}
          </strong>
        </div>
        <div>
          <Gauge size={18} />
          <span>90th percentile</span>
          <strong>{p90 === null ? 'Not available' : seconds(p90)}</strong>
        </div>
        <div>
          <CircleAlert size={18} />
          <span>Failed / timed out / stopped</span>
          <strong>
            {measurements.filter((item) => item.outcome === 'failed').length} /{' '}
            {measurements.filter((item) => item.outcome === 'timed-out').length}
            {' / '}
            {measurements.filter((item) => item.outcome === 'stopped').length}
          </strong>
        </div>
      </div>
      <TokenCost
        usages={measurements
          .filter((item) => item.outcome === 'completed')
          .map((item) => item.usage ?? null)}
        budgetAlerts={budgetAlerts}
      />
      <h2 className="request-heading" id="recent-heading">
        Recent requests
      </h2>
      {measurements.length ? (
        <div className="request-table-wrap">
          <table className="request-table" aria-labelledby="recent-heading">
            <thead>
              <tr>
                <th scope="col">Agent</th>
                <th scope="col">Outcome</th>
                <th scope="col">Elapsed</th>
              </tr>
            </thead>
            <tbody>
              {measurements
                .slice(-20)
                .reverse()
                .map((item) => (
                  <tr key={item.id}>
                    <td>{item.agent}</td>
                    <td>{item.outcome}</td>
                    <td>{seconds(item.duration)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
          <button type="button" className="inline-link" onClick={onLog}>
            See references and errors in the request log
          </button>
        </div>
      ) : (
        <div className="metrics-empty">
          <Activity size={30} strokeWidth={1.2} />
          <h2>No live requests yet</h2>
          <span>
            {preview
              ? 'Local preview makes no model calls, so nothing is measured.'
              : 'Send a message in Chat to start measuring.'}
          </span>
        </div>
      )}
      <p className="table-note">
        To compare agents, open one in the Agent library and choose{' '}
        <strong>Test results</strong>. It shows how the agent did on its
        recorded test cases, with typical response time and model cost.
      </p>
    </main>
  )
}
