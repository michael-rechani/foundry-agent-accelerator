import { Activity, CircleAlert, Clock3, MessageSquare } from 'lucide-react'

export type Measurement = {
  id: string
  agent: string
  outcome: 'completed' | 'failed' | 'stopped' | 'timed-out'
  duration: number
}

export function PerformanceView({
  measurements,
}: {
  measurements: Measurement[]
}) {
  const completed = measurements.filter((item) => item.outcome === 'completed')
  const average = completed.length
    ? completed.reduce((total, item) => total + item.duration, 0) /
      completed.length
    : null
  return (
    <main className="secondary-view">
      <div className="section-heading">
        <h1>Performance</h1>
        <p>Requests and response times from this browser session.</p>
      </div>
      <div className="metric-strip">
        <div>
          <MessageSquare size={18} />
          <span>Completed</span>
          <strong>{completed.length}</strong>
        </div>
        <div>
          <Clock3 size={18} />
          <span>Average response</span>
          <strong>
            {average === null
              ? 'Not available'
              : `${(average / 1000).toFixed(1)}s`}
          </strong>
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
      <h2 className="request-heading">Recent requests</h2>
      {measurements.length ? (
        <div className="request-table-wrap">
          <table className="request-table">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Outcome</th>
                <th>Elapsed</th>
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
                    <td>{(item.duration / 1000).toFixed(1)}s</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="metrics-empty">
          <Activity size={30} strokeWidth={1.2} />
          <h2>No live requests yet</h2>
        </div>
      )}
    </main>
  )
}
