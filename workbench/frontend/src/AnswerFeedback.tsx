import { ThumbsDown, ThumbsUp } from 'lucide-react'
import { useId } from 'react'
import { maxReasonLength } from './answer-feedback'
import type { Rating } from './conversation-types'

// Thumbs up or down under an answer, with an optional short reason. Choosing
// the same thumb again clears the rating.
export function AnswerFeedback({
  rating,
  onRate,
}: {
  rating?: Rating
  onRate: (rating: Rating | undefined) => void
}) {
  const reasonId = useId()
  const choose = (value: Rating['value']) =>
    onRate(rating?.value === value ? undefined : { value })
  return (
    <div className="answer-feedback" role="group" aria-label="Rate this answer">
      <button
        type="button"
        className="chat-icon"
        title="Helpful"
        aria-label="Helpful"
        aria-pressed={rating?.value === 'up'}
        onClick={() => choose('up')}
      >
        <ThumbsUp size={15} />
      </button>
      <button
        type="button"
        className="chat-icon"
        title="Not helpful"
        aria-label="Not helpful"
        aria-pressed={rating?.value === 'down'}
        onClick={() => choose('down')}
      >
        <ThumbsDown size={15} />
      </button>
      {rating && (
        <>
          <label className="answer-feedback-reason" htmlFor={reasonId}>
            <span className="visually-hidden">Reason (optional)</span>
            <input
              id={reasonId}
              type="text"
              value={rating.reason ?? ''}
              maxLength={maxReasonLength}
              placeholder="Why? (optional)"
              onChange={(event) =>
                onRate({ value: rating.value, reason: event.target.value })
              }
            />
          </label>
          <small>Kept in this tab and in Export only.</small>
        </>
      )}
    </div>
  )
}
