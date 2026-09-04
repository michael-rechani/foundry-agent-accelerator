# Synthetic review requests

These fixtures contain no real applicant or case data. Submit each request
separately so a single specialist should handle it.

## Application review

Review this application against the supplied criterion. Preserve source IDs
and identify missing evidence without making an approval or denial decision.

- CRIT-1: the application must include an itemized budget.
- APP-1: the applicant proposes three training sessions with two facilitators.
  No budget, rates, or cost totals are included in this supplied document.

Return the application specialist's finding and a clarification question.

Expected verification: `review_application` executes; its matching successful
tool result is nonempty. The result should identify the missing budget using
CRIT-1 and APP-1. Do not infer that a budget is absent from records not supplied.

## Case review

Review the supplied case record for chronology and conflicting evidence.
Preserve source IDs and avoid deciding which source is correct without support.

- CASE-1: intake was recorded on June 1, 2026.
- CASE-2: intake was recorded on June 3, 2026.
- CASE-3: the follow-up appointment was recorded on June 8, 2026.

Return the case specialist's findings and the clarification needed to reconcile
the intake dates. Do not decide liability, eligibility, or an enforcement outcome.

Expected verification: `review_case` executes; its matching successful tool
result is nonempty. The result should identify the CASE-1/CASE-2 date conflict
and preserve CASE-3 as a separate event.