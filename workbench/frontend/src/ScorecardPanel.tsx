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
  formatAnswersPassed,
  formatCostPerAnswer,
  formatDate,
  formatExactCost,
  formatSeconds,
  formatTimes,
} from './scorecards'
import { formatTokens } from './token-usage'

const ANSWER_SOURCES = {
  lab: 'Answers were recorded in the Lab.',
  direct:
    'Answers, response times and token counts were recorded by running the agent’s current instructions against the Lab’s Foundry project, so times can differ slightly from the live Lab. The first answer to each request is the recorded one a person reads. The repeat answers are checked automatically.',
  mixed: 'Answers were recorded in more than one run.',
}

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
  const allPassed = summary.runs_passed === summary.runs
  const missed = summary.cases - summary.passed
  return (
    <section className="scorecard" aria-labelledby="scorecard-title">
      <div className="scorecard-heading">
        <h2 id="scorecard-title">How it did on its test cases</h2>
        <p className="library-muted">
          Tested on {formatDate(card.tested_on)} with sample data. Each case
          sends the agent a sample request {formatTimes(summary.runs_per_case)}
          and checks every answer for the facts, questions and limits it should
          show. The same request can get a different answer each time, so a case
          only passes when every answer passes.
        </p>
      </div>
      <dl className="library-facts scorecard-facts">
        <div>
          <dt>
            <ListChecks size={15} aria-hidden="true" /> Answer checks
          </dt>
          <dd>
            <strong>
              {formatAnswersPassed(summary.runs_passed, summary.runs)}
            </strong>
            <span>
              {allPassed
                ? `${summary.cases} test cases, each asked ${formatTimes(summary.runs_per_case)}. Every answer met its checks.`
                : `${missed} of ${summary.cases} test ${missed === 1 ? 'case has' : 'cases have'} an answer that missed a check, so a person needs to look.`}
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
              {card.signed_off && card.signed_off_by && card.signed_off_on
                ? `Read by ${card.signed_off_by} on ${formatDate(card.signed_off_on)}.`
                : "A person reads the recorded answer to every test case before it's marked ready."}
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
                <span className="scorecard-case-runs">
                  {formatAnswersPassed(item.runs_passed, item.runs)}
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
        <strong>Needs a look</strong> means at least one answer missed an
        automatic check, such as a required figure, a follow-up question or a
        claim the sample data doesn&apos;t support. Some of these are wording
        the check doesn&apos;t recognize, so a person reads the answer against
        its goal. Passing the checks isn&apos;t a promise that every answer is
        right, which is why a person still reads the recorded answers.
      </p>
      <p className="library-muted hood-only">
        <CalendarCheck size={13} aria-hidden="true" /> Model {card.model}.{' '}
        {ANSWER_SOURCES[card.answers_from]} Answers were recorded with dataset{' '}
        {scorecards.answers_dataset} and checked with{' '}
        {scorecards.checks_dataset} (<code>evaluations/library-cases.json</code>
        ). Costs count model tokens only, at {prices.currency} list prices for{' '}
        {prices.deployment_type} in {prices.region}, retrieved{' '}
        {formatDate(prices.retrieved_on)}. Hosting, storage and monitoring
        aren&apos;t included.
      </p>
    </section>
  )
}
