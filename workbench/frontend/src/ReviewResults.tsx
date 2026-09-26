import { ArrowRight, FileText, Plus } from 'lucide-react'
import type { Review, Run } from './review-client'

export function ReviewResults({
  review,
  run,
  runIndex,
  currentDraft,
  busy,
  additional,
  onCitation,
  onAdditional,
  onAddEvidence,
}: {
  review: Review
  run?: Run
  runIndex: number
  currentDraft: boolean
  busy: boolean
  additional: string
  onCitation: (sourceId: string) => void
  onAdditional: (value: string) => void
  onAddEvidence: () => void
}) {
  return (
    <>
      {run?.result ? (
        <>
          <h2>{currentDraft ? 'Previous run summary' : 'Review summary'}</h2>
          <p className="review-summary">{run.result.summary}</p>
          <span className="review-disclaimer">
            Quotes point to your documents; they do not prove those documents
            are true. Check the results yourself. They do not approve
            applications or make business decisions.
          </span>
          {run.result.findings.map((finding) => (
            <article className="review-finding" key={finding.criterion_id}>
              <div>
                <span className={`finding-label finding-${finding.assessment}`}>
                  {finding.assessment}
                </span>
                <span className="micro-label">
                  Checklist item {finding.criterion_id.slice(5)}
                </span>
              </div>
              <h3>
                {run.input.criteria[Number(finding.criterion_id.slice(5)) - 1]}
              </h3>
              <p>{finding.explanation}</p>
              {finding.citations.map((citation, index) => (
                <blockquote key={index}>
                  <button onClick={() => onCitation(citation.source_id)}>
                    <FileText size={14} />
                    Document {citation.source_id.slice(4)}
                    <ArrowRight size={14} />
                  </button>
                  <p>{citation.quote}</p>
                </blockquote>
              ))}
            </article>
          ))}
        </>
      ) : (
        <>
          <h2>Your checklist</h2>
          <ol className="review-criteria">
            {review.criteria.map((criterion, index) => (
              <li key={index}>
                <span className="micro-label">Checklist item {index + 1}</span>
                <p>{criterion}</p>
              </li>
            ))}
          </ol>
        </>
      )}
      {review.status === 'waiting_input' &&
        (runIndex < 0 || runIndex === review.runs.length - 1) && (
          <form
            className="clarification-form"
            onSubmit={(event) => {
              event.preventDefault()
              onAddEvidence()
            }}
          >
            <h2>More information needed</h2>
            <ul>
              {run?.result?.questions.map((question, index) => (
                <li key={index}>{question}</li>
              ))}
            </ul>
            <p className="review-hint">
              Add the missing details or explain which statement is correct.
              Save them, then choose Review again.
            </p>
            <label>
              More information
              <textarea
                required
                rows={5}
                maxLength={12000}
                value={additional}
                onChange={(event) => onAdditional(event.target.value)}
              />
            </label>
            <button
              className="review-primary"
              disabled={
                busy || review.runs.length >= 4 || review.evidence.length >= 12
              }
            >
              <Plus size={16} />
              Save added information
            </button>
            {review.runs.length >= 4 && <p>Run limit reached.</p>}
          </form>
        )}
    </>
  )
}
