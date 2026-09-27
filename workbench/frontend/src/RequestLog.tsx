import { Copy, ScrollText } from 'lucide-react'
import type { Measurement } from './performance-stats'

const outcomes: Record<Measurement['outcome'], string> = {
  completed: 'Completed',
  failed: 'Failed',
  stopped: 'Stopped',
  'timed-out': 'Timed out',
}

export function RequestLog({
  measurements,
  preview,
  onCopy,
}: {
  measurements: Measurement[]
  preview: boolean
  onCopy: (text: string) => void
}) {
  const entries = [...measurements].reverse()
  return (
    <main className="secondary-view">
      <div className="section-heading">
        <h1>Request log</h1>
        <p>
          Every live agent request from this browser tab, newest first. Give an
          operator the reference to find the matching server log entry. Message
          text is not recorded here, and the log clears when the page reloads.
        </p>
      </div>
      {entries.length ? (
        <div className="request-table-wrap">
          <table className="request-table request-log" aria-label="Request log">
            <thead>
              <tr>
                <th scope="col">Time</th>
                <th scope="col">Agent</th>
                <th scope="col">Outcome</th>
                <th scope="col">Elapsed</th>
                <th scope="col">Reference</th>
                <th scope="col">Details</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((item) => (
                <tr key={item.id} data-outcome={item.outcome}>
                  <td>
                    <time dateTime={new Date(item.at).toISOString()}>
                      {new Date(item.at).toLocaleTimeString()}
                    </time>
                  </td>
                  <td>{item.agent}</td>
                  <td>
                    <span className={`log-outcome ${item.outcome}`}>
                      {outcomes[item.outcome]}
                    </span>
                  </td>
                  <td>{(item.duration / 1000).toFixed(1)}s</td>
                  <td>
                    {item.reference ? (
                      <button
                        type="button"
                        className="log-reference"
                        title="Copy reference"
                        aria-label={`Copy reference ${item.reference}`}
                        onClick={() => onCopy(item.reference!)}
                      >
                        <code>{item.reference}</code>
                        <Copy size={13} aria-hidden="true" />
                      </button>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>{item.message || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="metrics-empty">
          <ScrollText size={30} strokeWidth={1.2} />
          <h2>No requests logged yet</h2>
          <span>
            {preview
              ? 'Local preview makes no model calls, so nothing is logged.'
              : 'Requests appear here after you send a message in Chat.'}
          </span>
        </div>
      )}
    </main>
  )
}
