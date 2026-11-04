import { useEffect, useRef, useState } from 'react'
import {
  Check,
  ClipboardCheck,
  Download,
  LoaderCircle,
  Play,
  Sparkles,
  Square,
  X,
} from 'lucide-react'
import { creationRequest, parseDraft } from './agent-creation-client'
import { specGoal, type AgentSpec } from './agent-spec'
import type { ChatFailure } from './chat-failure'
import {
  asFailure,
  describeChecks,
  designRequest,
  failedRuns,
  lineDiff,
  MAX_REPEATS,
  MAX_REVISIONS,
  PASS_SAMPLE,
  parseCaseDraft,
  parseCaseRun,
  parseRevision,
  pendingJobs,
  regressions,
  rerunScope,
  revisionRequest,
  summarizeRuns,
  testFile,
  testFileName,
  type CaseRun,
  type Revision,
  type Round,
  type TestCase,
} from './design-loop-client'
import { saveFile } from './save-file'
import { formatTokens, totalUsage, type Usage } from './token-usage'

// What the chat needs to run a draft's tests: the browser's time limit for one
// model call. Only given when the Lab's library previews are on.
export type SpecTests = { timeoutMs: number; active?: boolean }

const stopped =
  'Stopped. A call already sent may still finish and use the model.'

const plural = (count: number, word: string) =>
  `${count} ${word}${count === 1 ? '' : 's'}`

// Tries a draft before anything is published. The text it tests is the exact
// setup Create agent would publish, prepared by the Lab from the template the
// spec points to, so a pass or fail says something about that setup. Every
// model call is one request the person asked for after confirming the cost.
// When cases fail, a model may propose a revision of the task instructions
// only; nothing changes until the person accepts it, and accepting hands the
// text to the Create button so what is tested is what would be published.
export function SpecTestPanel({
  spec,
  templateId,
  templateLabel,
  tests,
  onAccept,
  disabled = false,
}: {
  spec: AgentSpec
  templateId: string
  templateLabel: string
  tests: SpecTests
  // Called with the accepted instructions, or null when the draft starts over.
  onAccept?: (instructions: string | null) => void
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [consent, setConsent] = useState(false)
  const [stage, setStage] = useState<
    'idle' | 'writing' | 'running' | 'revising'
  >('idle')
  const [instructions, setInstructions] = useState('')
  const [cases, setCases] = useState<TestCase[]>([])
  const [dropped, setDropped] = useState(0)
  const [writerUsage, setWriterUsage] = useState<Usage | null>(null)
  const [repeats, setRepeats] = useState(1)
  const [results, setResults] = useState<Record<string, CaseRun[]>>({})
  // Earlier versions of the instructions with their results, and the cases a
  // later round runs again. Null means every case runs.
  const [rounds, setRounds] = useState<Round[]>([])
  const [scope, setScope] = useState<string[] | null>(null)
  const [revision, setRevision] = useState<Revision | null>(null)
  const [revisionUsage, setRevisionUsage] = useState<(Usage | null)[]>([])
  const [failure, setFailure] = useState<ChatFailure | null>(null)
  const [notice, setNotice] = useState('')
  const controller = useRef<AbortController | null>(null)
  const working = stage !== 'idle'

  useEffect(() => () => controller.current?.abort(), [])
  useEffect(() => {
    if (tests.active === false) controller.current?.abort()
  }, [tests.active])

  const scoped = scope ? cases.filter((test) => scope.includes(test.id)) : cases
  const jobs = pendingJobs(scoped, results, repeats)
  const summary = summarizeRuns(scoped, results)
  const failed = failedRuns(scoped, results)
  const lastRound = rounds.at(-1)
  const usage = totalUsage([
    ...(cases.length ? [writerUsage] : []),
    ...revisionUsage,
    ...cases.flatMap((test) =>
      [...rounds.map((round) => round.results), results].flatMap((set) =>
        (set[test.id] ?? []).map((run) => run.usage),
      ),
    ),
  ])
  const started = summary.runs > 0
  const slipped = lastRound
    ? regressions(scoped, lastRound.results, results)
    : []
  const notRerun = cases.length - scoped.length
  const nextScope = revision ? rerunScope(scoped, results) : []

  async function writeCases() {
    if (working || disabled || !consent) return
    const run = new AbortController()
    controller.current = run
    setStage('writing')
    setFailure(null)
    setNotice('')
    try {
      const draft = parseDraft(
        await creationRequest(
          'agent-drafts',
          {
            method: 'POST',
            body: JSON.stringify({
              goal: specGoal(spec),
              template_id: templateId,
            }),
          },
          run.signal,
        ),
      )
      if (draft.template_id !== templateId)
        throw new Error(
          'The prepared setup does not match the template this spec points to.',
        )
      const written = parseCaseDraft(
        await designRequest(
          'agent-test-cases',
          {
            instructions: draft.instructions,
            template_id: templateId,
            confirm_cost: true,
          },
          tests.timeoutMs,
          run.signal,
        ),
      )
      setInstructions(draft.instructions)
      setCases(written.cases)
      setDropped(written.dropped)
      setWriterUsage(written.usage)
      setResults({})
      setRounds([])
      setScope(null)
      setRevision(null)
      setRevisionUsage([])
      onAccept?.(null)
    } catch (problem) {
      if (run.signal.aborted) setNotice(stopped)
      else setFailure(asFailure(problem))
    } finally {
      setStage('idle')
    }
  }

  async function runTests() {
    if (working || disabled || !consent || !jobs.length) return
    const run = new AbortController()
    controller.current = run
    setStage('running')
    setFailure(null)
    setNotice('')
    try {
      for (const job of jobs) {
        const outcome = parseCaseRun(
          await designRequest(
            'agent-test-runs',
            {
              instructions,
              template_id: templateId,
              case: job.test,
              confirm_cost: true,
            },
            tests.timeoutMs,
            run.signal,
          ),
        )
        setResults((previous) => ({
          ...previous,
          [job.test.id]: [...(previous[job.test.id] ?? []), outcome],
        }))
      }
    } catch (problem) {
      if (run.signal.aborted) setNotice(stopped)
      else setFailure(asFailure(problem))
    } finally {
      setStage('idle')
    }
  }

  async function proposeRevision() {
    if (working || disabled || !consent || !failed.length || revision) return
    const run = new AbortController()
    controller.current = run
    setStage('revising')
    setFailure(null)
    setNotice('')
    try {
      const proposed = parseRevision(
        await designRequest(
          'agent-test-revisions',
          revisionRequest({ instructions, templateId, failed }),
          tests.timeoutMs,
          run.signal,
        ),
      )
      setRevision(proposed)
      setRevisionUsage((previous) => [...previous, proposed.usage])
    } catch (problem) {
      if (run.signal.aborted) setNotice(stopped)
      else setFailure(asFailure(problem))
    } finally {
      setStage('idle')
    }
  }

  function accept() {
    if (!revision || working) return
    const rerun = rerunScope(scoped, results)
    setRounds((previous) => [
      ...previous,
      { instructions, changes: revision.changes, results },
    ])
    setScope(rerun)
    setResults({})
    setInstructions(revision.instructions)
    onAccept?.(revision.instructions)
    setNotice(
      `Revision accepted. Nothing is published yet. Run ${plural(rerun.length, 'case')} again to see whether it helped.`,
    )
    setRevision(null)
  }

  function download() {
    saveFile(
      testFileName(spec),
      JSON.stringify(
        testFile({
          name: spec.name,
          templateId,
          instructions,
          cases,
          results,
          rounds,
        }),
        null,
        2,
      ) + '\n',
      'application/json',
    )
  }

  if (!open)
    return (
      <div className="agent-spec-actions">
        <button
          type="button"
          className="library-secondary"
          onClick={() => setOpen(true)}
        >
          <ClipboardCheck size={16} aria-hidden="true" /> Test this draft first
        </button>
      </div>
    )

  return (
    <div
      className="spec-build spec-test"
      role="group"
      aria-label="Test this draft"
    >
      <h5>Test {spec.name} before you publish it</h5>
      <p>
        A model writes sample test cases for this draft, then runs them against
        the <strong>{templateLabel}</strong> setup this spec would publish.
        Nothing is published or saved in the Lab.
      </p>
      <ul>
        <li>Writing the cases is one call to the shared Foundry model.</li>
        <li>
          Each test is one more call, sent one at a time. You choose how many
          times to repeat them.
        </li>
        <li>
          If tests fail, you can ask for a revised task text: one more call.
          Nothing changes until you accept it, and you can do this{' '}
          {MAX_REVISIONS} times at most.
        </li>
        <li>
          Simple checks screen the answers. A person still has to read each
          answer against its rubric.
        </li>
        <li>
          Switching pages keeps these results and pauses further test calls. A
          call already sent may still finish and incur charges. Returning to
          Chat does not restart it automatically.
        </li>
      </ul>
      <label className="creation-consent">
        <input
          type="checkbox"
          checked={consent}
          disabled={working}
          onChange={(event) => setConsent(event.target.checked)}
        />
        <span>
          I confirm each test or revision call uses the shared Foundry model and
          can incur charges.
        </span>
      </label>
      {!cases.length && (
        <div className="agent-spec-actions">
          <button
            type="button"
            className="library-secondary spec-test-write"
            disabled={working || disabled || !consent}
            onClick={() => void writeCases()}
          >
            {stage === 'writing' ? (
              <LoaderCircle size={16} className="spin" aria-hidden="true" />
            ) : (
              <ClipboardCheck size={16} aria-hidden="true" />
            )}
            Write test cases
          </button>
          <button
            type="button"
            className="inline-link"
            disabled={working}
            onClick={() => {
              setOpen(false)
              setFailure(null)
              setNotice('')
            }}
          >
            Cancel
          </button>
        </div>
      )}
      {stage === 'writing' && (
        <p className="spec-build-status" role="status">
          Preparing the setup and writing test cases…
        </p>
      )}
      {!!cases.length && (
        <>
          <h5>
            {plural(cases.length, 'test case')}
            {dropped > 0 && (
              <span className="agent-spec-note">
                {' '}
                ({plural(dropped, 'drafted case')} dropped for failing the
                Lab&apos;s checks)
              </span>
            )}
          </h5>
          <ol className="spec-test-cases" aria-label="Test cases">
            {cases.map((test) => {
              const runs = results[test.id] ?? []
              const lines = describeChecks(test.checks)
              const skipped = scope !== null && !scope.includes(test.id)
              const before = lastRound?.results[test.id]
              return (
                <li key={test.id}>
                  <p>
                    <strong>{test.id}</strong>{' '}
                    <span className="spec-test-category">{test.category}</span>
                  </p>
                  <p>{test.input}</p>
                  <p className="agent-spec-note">Rubric: {test.rubric}</p>
                  {!!lines.length && (
                    <p className="agent-spec-note">
                      Screen: {lines.join(' · ')}
                    </p>
                  )}
                  {skipped && (
                    <p className="agent-spec-note">
                      Not run against the current instructions. It passed under
                      an earlier version.
                    </p>
                  )}
                  {!skipped && !!before?.length && (
                    <p className="agent-spec-note">
                      Earlier version:{' '}
                      {before.every((run) => run.passed)
                        ? 'passed'
                        : 'did not pass'}{' '}
                      the checks.
                    </p>
                  )}
                  {runs.map((run, index) => (
                    <div
                      key={run.request_id}
                      className={`spec-test-run ${run.passed ? 'passed' : 'flagged'}`}
                    >
                      <p>
                        <strong>
                          {run.passed
                            ? 'Passed the checks'
                            : 'Did not pass the checks'}
                        </strong>
                        {runs.length > 1 && ` (run ${index + 1})`}
                      </p>
                      {!!run.failures.length && (
                        <ul>
                          {run.failures.map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      )}
                      <p className="agent-spec-note">
                        {run.receipts.length
                          ? 'Lookups called: ' +
                            run.receipts.map((item) => item.tool).join(', ')
                          : 'No lookups called.'}
                      </p>
                      <details>
                        <summary>Read the answer</summary>
                        <pre className="spec-test-answer">{run.text}</pre>
                      </details>
                    </div>
                  ))}
                </li>
              )
            })}
          </ol>
          <div className="agent-spec-actions">
            <label className="spec-test-repeats">
              Repeat each test{' '}
              <select
                value={repeats}
                disabled={working}
                onChange={(event) => setRepeats(Number(event.target.value))}
              >
                {Array.from(
                  { length: MAX_REPEATS },
                  (_, index) => index + 1,
                ).map((value) => (
                  <option key={value} value={value}>
                    {value}×
                  </option>
                ))}
              </select>
            </label>
            {working && stage === 'running' ? (
              <button
                type="button"
                className="library-secondary"
                onClick={() => controller.current?.abort()}
              >
                <Square size={16} aria-hidden="true" /> Stop
              </button>
            ) : (
              <button
                type="button"
                className="library-secondary spec-test-run-button"
                disabled={working || disabled || !consent || !jobs.length}
                onClick={() => void runTests()}
              >
                <Play size={16} aria-hidden="true" />
                {started && jobs.length
                  ? `Continue (${plural(jobs.length, 'test call')} left)`
                  : jobs.length
                    ? `Run ${plural(jobs.length, 'test call')}`
                    : 'All tests run'}
              </button>
            )}
            <button
              type="button"
              className="library-secondary"
              disabled={working}
              onClick={download}
            >
              <Download size={16} aria-hidden="true" /> Download cases and
              results
            </button>
            <button
              type="button"
              className="inline-link"
              disabled={working || disabled || !consent}
              onClick={() => void writeCases()}
            >
              {rounds.length ? 'Start over with new cases' : 'Write new cases'}
            </button>
          </div>
          {!!failed.length && !revision && stage !== 'revising' && (
            <div className="spec-test-revise">
              {rounds.length < MAX_REVISIONS ? (
                <>
                  <p>
                    {plural(failed.length, 'case')} did not pass the checks. A
                    model can propose a revision of the task instructions from{' '}
                    {failed.length > 5 ? 'the first 5' : 'them'}. That is one
                    more call, and the checks, the tools and the fixed policy
                    stay as they are.
                  </p>
                  <div className="agent-spec-actions">
                    <button
                      type="button"
                      className="library-secondary spec-test-revise-button"
                      disabled={working || disabled || !consent}
                      onClick={() => void proposeRevision()}
                    >
                      <Sparkles size={16} aria-hidden="true" /> Propose a
                      revision (1 call)
                    </button>
                  </div>
                </>
              ) : (
                <p className="agent-spec-note">
                  {MAX_REVISIONS} revisions is the limit here. Read the failed
                  answers and change the instructions yourself in Create agent.
                </p>
              )}
            </div>
          )}
          {stage === 'revising' && (
            <p className="spec-build-status" role="status">
              <LoaderCircle size={16} className="spin" aria-hidden="true" />{' '}
              Asking for a revision…
              <button
                type="button"
                className="inline-link"
                onClick={() => controller.current?.abort()}
              >
                Stop
              </button>
            </p>
          )}
          {revision && (
            <div
              className="spec-test-revision"
              role="group"
              aria-label="Proposed revision"
            >
              <h5>
                Proposed revision {rounds.length + 1} of {MAX_REVISIONS}
              </h5>
              <ul>
                {revision.changes.map((change) => (
                  <li key={change}>{change}</li>
                ))}
              </ul>
              <ul
                className="spec-test-diff"
                aria-label="Changes to the task instructions"
              >
                {lineDiff(instructions, revision.instructions).map(
                  (line, index) => (
                    <li key={`${index}:${line.kind}`} className={line.kind}>
                      <span aria-hidden="true">
                        {line.kind === 'add'
                          ? '+ '
                          : line.kind === 'remove'
                            ? '− '
                            : '  '}
                      </span>
                      <span className="visually-hidden">
                        {line.kind === 'add'
                          ? 'Added: '
                          : line.kind === 'remove'
                            ? 'Removed: '
                            : 'Unchanged: '}
                      </span>
                      {line.text || ' '}
                    </li>
                  ),
                )}
              </ul>
              <p className="agent-spec-note">
                Accepting replaces the task instructions this panel tests and
                the Create button below would publish. Nothing is published or
                saved by accepting. You then run{' '}
                {plural(nextScope.length, 'case')} again: the failed ones plus
                up to {PASS_SAMPLE} that passed, to catch a change that broke
                them. Cases outside that sample are not run again.
              </p>
              <div className="agent-spec-actions">
                <button
                  type="button"
                  className="library-secondary spec-test-accept"
                  disabled={working}
                  onClick={accept}
                >
                  <Check size={16} aria-hidden="true" /> Accept revision
                </button>
                <button
                  type="button"
                  className="library-secondary spec-test-discard"
                  disabled={working}
                  onClick={() => setRevision(null)}
                >
                  <X size={16} aria-hidden="true" /> Discard
                </button>
              </div>
            </div>
          )}
          {stage === 'running' && (
            <p className="spec-build-status" role="status">
              <LoaderCircle size={16} className="spin" aria-hidden="true" />{' '}
              Running test {summary.runs + 1} of {summary.runs + jobs.length}…
            </p>
          )}
          {started && (
            <p className="spec-test-summary" role="status">
              {summary.passed} of {plural(summary.runs, 'run')} passed the
              automatic checks
              {rounds.length > 0 && ' under the revised instructions'}. That is
              not proof the draft is right: read each answer against its rubric.
            </p>
          )}
          {slipped.length > 0 && (
            <p className="spec-build-error" role="status">
              Passed before the revision but does not now: {slipped.join(', ')}.
              The revision may have broken it.
            </p>
          )}
          {notRerun > 0 && (
            <p className="agent-spec-note">
              {plural(notRerun, 'case')} not run against the current
              instructions.
            </p>
          )}
          {usage.measured + usage.missing > 0 && (
            <p className="agent-spec-note">
              {formatTokens(usage.total)} tokens across{' '}
              {plural(usage.measured, 'call')}
              {usage.missing > 0 &&
                `; ${plural(usage.missing, 'call')} did not report tokens`}
              . Results stay on this page; download them to keep them.
            </p>
          )}
        </>
      )}
      {notice && (
        <p className="agent-spec-note" role="status">
          {notice}
        </p>
      )}
      {failure && (
        <p className="spec-build-error" role="alert">
          {failure.message}
          {failure.reference && (
            <>
              {' '}
              Reference: <code>{failure.reference}</code>
            </>
          )}
        </p>
      )}
    </div>
  )
}
