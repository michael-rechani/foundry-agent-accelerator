import type { DemoScenario } from './demo-scenarios'
import './showcase.css'

export function DemoBrief({
  scenario,
  showExpected = false,
  inAnswer = false,
}: {
  scenario: DemoScenario
  showExpected?: boolean
  inAnswer?: boolean
}) {
  return (
    <section
      className={`demo-brief${inAnswer ? ' demo-brief-in-answer' : ''}`}
      aria-label="Demo story"
    >
      <dl>
        <div>
          <dt>Problem statement</dt>
          <dd>{scenario.problem}</dd>
        </div>
        <div>
          <dt>What the agent does</dt>
          <dd>{scenario.agentDoes}</dd>
        </div>
        {showExpected && (
          <div className="demo-expected">
            <dt>Expected sample result</dt>
            <dd>
              <p>{scenario.expectedReturn}</p>
              <p className="demo-brief-note">
                A target to check, not an answer the agent has returned.
              </p>
            </dd>
          </div>
        )}
      </dl>
      {!inAnswer && <p className="demo-brief-note">{scenario.decision}</p>}
    </section>
  )
}
