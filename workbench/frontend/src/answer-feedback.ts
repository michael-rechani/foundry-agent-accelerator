import type { Rating, Turn } from './conversation-types'

export const maxReasonLength = 200

// The turns with one answer's rating set, changed or cleared.
export function withRating(
  turns: Turn[],
  index: number,
  rating: Rating | undefined,
): Turn[] {
  return turns.map((turn, position) => {
    if (position !== index) return turn
    const { rating: _previous, ...rest } = turn
    if (!rating) return rest
    const reason = rating.reason?.slice(0, maxReasonLength)
    return {
      ...rest,
      rating: reason ? { ...rating, reason } : { value: rating.value },
    }
  })
}

// A short line for the side panel, or '' when nothing was rated.
export function summarizeRatings(turns: Turn[]) {
  const helpful = turns.filter((turn) => turn.rating?.value === 'up').length
  const notHelpful = turns.filter(
    (turn) => turn.rating?.value === 'down',
  ).length
  return [
    helpful && `${helpful} helpful`,
    notHelpful && `${notHelpful} not helpful`,
  ]
    .filter(Boolean)
    .join(', ')
}
