import {
  CalendarCheck,
  CircleCheck,
  Clock3,
  Eye,
  ListChecks,
  RefreshCw,
  UserCheck,
  Wallet,
} from 'lucide-react'
import type { ScorecardsState } from './scorecards-client'
import {
  categoryTitles,
  formatCostPerAnswer,
  formatDate,
  formatExactCost,
  formatSeconds,
} from './scorecards'
import { formatTokens } from './token-usage'

export function ScorecardPanel({
  templateId,
  state,
}: {
  templateId: string
  state: ScorecardsState
}) {
  const { scorecards, error, retry } = state
  if (error)
    return (
      <section className="library-panel scorecard-empty" role="alert">
        <p>The test results didn&apos;t load. {error}</p>
        <button type="button" className="library-secondary" onClick={retry}>
          <RefreshCw size={15} /> Try again
        </button>
      </section>
    )
  if (!scorecards)
    return (
      <section className="library-panel scorecard-empty" aria-busy="true">
        <p>Loading test results…</p>
      </section>
    )
  const card = scorecards.scorecards.find(
    (item) => item.template_id === templateId,
  )
  if (!card)
    return (
      <section className="library-panel scorecard-empty">
        <h2>No test results yet</h2>
        <p>
          This agent hasn&apos;t been through a recorded test run. Try it with
          the example to see how it answers.
        </p>
      </section>
    )
  const { summary } = card
  const { prices } = scorecards
  const allPassed = summary.passed === summary.cases
  return (
    <section className="scorecard" aria-labelledby="scorecard-title">
      <div className="scorecard-heading">
        <h2 id="scorecard-title">How it did on its test cases</h2>
        <p className="library-muted">
          Tested on {formatDate(card.tested_on)} with sample data. Each case
          sends the agent a sample request and checks the answer for the facts,
          questions and limits it should show.
        </p>
      </div>
      <dl className="library-facts scorecard-facts">
        <div>
          <dt>
            <ListChecks size={15} aria-hidden="true" /> Answer checks
          </dt>
          <dd>
            <strong>
              {summary.passed} of {summary.cases} passed
            </strong>
            <span>
              {allPassed
                ? 'Every answer met its checks.'
                : `${summary.cases - summary.passed} ${summary.cases - summary.passed === 1 ? 'answer needs' : 'answers need'} a person to look.`}
            </span>
          </dd>
        </div>
        <div>
          <dt>
            <Clock3 size={15} aria-hidden="true" /> Typical response
          </dt>
          <dd>
            <strong>{formatSeconds(summary.median_seconds)}</strong>
            <span>Median time to a full answer in the Lab.</span>
          </dd>
        </div>
        <div>
          <dt>
            <Wallet size={15} aria-hidden="true" /> Model cost per answer
          </dt>
          <dd>
            <strong>{formatCostPerAnswer(summary.average_cost_usd)}</strong>
            <span>Model use only, at Azure list prices.</span>
          </dd>
        </div>
        <div>
          <dt>
            <UserCheck size={15} aria-hidden="true" /> Sign-off
          </dt>
          <dd>
            <strong>
              {card.signed_off ? 'Signed off' : 'Waiting for a person'}
            </strong>
            <span>
              {card.signed_off
                ? 'A person has read these answers.'
                : "A person reads every answer before it's marked ready."}
            </span>
          </dd>
        </div>
      </dl>
      <ul className="scorecard-cases" aria-label="Test cases">
        {card.cases.map((item) => (
          <li key={item.id} className={item.passed ? 'passed' : 'review'}>
            {item.passed ? (
              <CircleCheck size={18} aria-hidden="true" />
            ) : (
              <Eye size={18} aria-hidden="true" />
            )}
            <div>
              <div className="scorecard-case-title">
                <strong>{categoryTitles[item.category]}</strong>
                <span
                  className={`library-badge ${item.passed ? 'good' : 'caution'}`}
                >
                  {item.passed ? 'Passed' : 'Needs a look'}
                </span>
              </div>
              <p>{item.goal}</p>
              <p className="scorecard-case-detail hood-only">
                <code>{item.id}</code> · {formatSeconds(item.seconds)} ·{' '}
                {formatTokens(item.input_tokens)} in (
                {formatTokens(item.cached_tokens)} cached),{' '}
                {formatTokens(item.output_tokens)} out ·{' '}
                {formatExactCost(item.cost_usd)}
              </p>
              {item.notes.length > 0 && (
                <ul className="scorecard-notes hood-only">
                  {item.notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              )}
            </div>
          </li>
        ))}
      </ul>
      <p className="library-muted">
        <strong>Needs a look</strong> means the answer missed at least one
        automatic check, such as a required figure or a follow-up question. Some
        of these are wording the check doesn&apos;t recognize, so a person reads
        the answer against its goal.
      </p>
      <p className="library-muted hood-only">
        <CalendarCheck size={13} aria-hidden="true" /> Model {card.model}.{' '}
        {card.answers_from === 'lab'
          ? 'Answers were recorded in the Lab.'
          : 'Answers come from a rerun after its instructions were updated; response times and token counts are from the earlier Lab run.'}{' '}
        Answers were recorded with dataset {scorecards.answers_dataset} and
        checked with {scorecards.checks_dataset} (
        <code>evaluations/library-cases.json</code>). Costs count model tokens
        only, at {prices.currency} list prices for {prices.deployment_type} in{' '}
        {prices.region}, retrieved {formatDate(prices.retrieved_on)}. Hosting,
        storage and monitoring aren&apos;t included.
      </p>
    </section>
  )
}
