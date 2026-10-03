import { useState } from 'react'
import { ArrowDownToLine, ArrowUpFromLine, Coins } from 'lucide-react'
import {
  estimateCost,
  formatTokens,
  loadRates,
  parseRates,
  storeRates,
  totalUsage,
  type Rates,
  type Usage,
} from './token-usage'

const billable = [
  [
    'Model tokens',
    'Every Chat message, including library previews. Input tokens grow with conversation length.',
  ],
  [
    'Tool round trips',
    'Each lookup sends the conversation back to the model, so an answer with tools uses several model calls.',
  ],
  [
    'Hosted agent runtime',
    'Published agents run in Foundry sandboxes billed for active and idle time.',
  ],
  [
    'Evaluations',
    'Acceptance and quality runs call models too, often with a separate grader model.',
  ],
  [
    'Logs and traces',
    'Log Analytics and Application Insights charge for ingestion and retention.',
  ],
] as const

export function TokenCost({
  usages,
  budgetAlerts = false,
}: {
  usages: (Usage | null)[]
  budgetAlerts?: boolean
}) {
  const totals = totalUsage(usages)
  const [rates, setRates] = useState<Rates | null>(() => loadRates())
  const [input, setInput] = useState(() => rates?.input.toString() ?? '')
  const [output, setOutput] = useState(() => rates?.output.toString() ?? '')
  const typed = parseRates({ input: Number(input), output: Number(output) })
  const apply = () => {
    const next = input.trim() && output.trim() ? typed : null
    setRates(next)
    storeRates(next)
  }
  const clear = () => {
    setInput('')
    setOutput('')
    setRates(null)
    storeRates(null)
  }
  return (
    <section className="token-cost" aria-labelledby="token-heading">
      <h2 className="request-heading" id="token-heading">
        Token usage and cost
      </h2>
      <div className="metric-strip">
        <div>
          <ArrowDownToLine size={18} />
          <span>Input tokens</span>
          <strong>{formatTokens(totals.input)}</strong>
        </div>
        <div>
          <ArrowUpFromLine size={18} />
          <span>Output tokens</span>
          <strong>{formatTokens(totals.output)}</strong>
        </div>
        <div>
          <Coins size={18} />
          <span>Estimated cost</span>
          <strong>
            {rates
              ? estimateCost(totals, rates).toLocaleString('en-US', {
                  maximumFractionDigits: 4,
                })
              : 'Add your rates'}
          </strong>
        </div>
      </div>
      <p className="table-note">
        Totals cover {totals.measured} completed{' '}
        {totals.measured === 1 ? 'reply' : 'replies'} in this tab
        {totals.missing
          ? `; ${totals.missing} did not report tokens and are not counted`
          : ''}
        . Output includes reasoning tokens. A coordinator&apos;s count may not
        include the specialists it calls.
      </p>
      <form
        className="rate-form"
        onSubmit={(event) => {
          event.preventDefault()
          apply()
        }}
      >
        <label>
          Input rate per 1M tokens
          <input
            inputMode="decimal"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="From your price sheet"
          />
        </label>
        <label>
          Output rate per 1M tokens
          <input
            inputMode="decimal"
            value={output}
            onChange={(event) => setOutput(event.target.value)}
            placeholder="From your price sheet"
          />
        </label>
        <button
          type="submit"
          disabled={!typed || !input.trim() || !output.trim()}
        >
          Use rates
        </button>
        {rates && (
          <button type="button" className="inline-link" onClick={clear}>
            Clear
          </button>
        )}
      </form>
      <p className="table-note">
        The Lab doesn&apos;t include prices. Rates you enter stay in this
        browser. The estimate is in the same currency as your rates, prices
        cached input at the full input rate, and isn&apos;t invoiced spend.
      </p>
      <h3 className="cost-heading">What costs money in the Lab</h3>
      <ul className="cost-list">
        {billable.map(([label, detail]) => (
          <li key={label}>
            <strong>{label}</strong> {detail}
          </li>
        ))}
      </ul>
      <p className="table-note" id="budget-alert-status">
        For monthly estimates, use the calculator in{' '}
        <code>cost-comparison/</code> in the repository.{' '}
        {budgetAlerts
          ? 'A monthly Azure budget on the Lab resource group emails alerts at 50%, 80% and 100% of the amount, and when spend is forecast to pass it. Budget alerts can arrive hours after the spend and don\u2019t stop anything.'
          : 'Azure budget alerts aren\u2019t set up for this Lab. An operator can turn them on; see \u201cBudget alerts\u201d in docs/lab-diagnostics.md.'}
      </p>
    </section>
  )
}
