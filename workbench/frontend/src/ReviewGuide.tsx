export function ReviewIntro() {
  return (
    <section className="review-intro" aria-label="Document review workflow">
      <p className="review-scope">
        Check the text you paste against your own checklist. See what is
        covered, what is missing and where documents disagree. Add more
        information and check again.
      </p>
      <ol className="review-steps">
        <li>Add a checklist and document text</li>
        <li>Run a review</li>
        <li>Read results beside the original text</li>
        <li>Add missing information and review again</li>
      </ol>
      <p className="review-hint">
        Chat is a conversation. A document review saves a separate check of each
        checklist item. Your Chat messages are not copied here, and review
        results are not sent back to Chat.
      </p>
    </section>
  )
}

export function ReviewGuide({ retentionDays }: { retentionDays: number }) {
  return (
    <details className="review-guide">
      <summary>How to read results and where your work is saved</summary>
      <dl className="finding-key">
        <div>
          <dt>Supported</dt>
          <dd>
            The text you supplied backs up this checklist item. That does not
            prove the text is true.
          </dd>
        </div>
        <div>
          <dt>Gap</dt>
          <dd>
            There is not enough information. This does not mean the application
            has failed.
          </dd>
        </div>
        <div>
          <dt>Conflict</dt>
          <dd>
            Statements disagree. Ask which one applies instead of guessing.
          </dd>
        </div>
      </dl>
      <p>
        A matching quote shows what a document says, not whether it is true.
        These results do not approve applications or make business decisions for
        you.
      </p>
      <p>
        In a connected Lab, Create shared review saves your checklist and
        document text. Each run also saves a copy of its input, results,
        follow-up questions and records of tool calls. Unsubmitted drafts stay
        in this browser until you leave or reload. Chat saves completed messages
        only when you choose Save.
      </p>
      <p>
        Anyone who can open this Lab can read saved reviews and add requested
        information. Records are not private to you; there are no individual
        user accounts. Use made-up examples only. Reviews expire {retentionDays}{' '}
        days after their last update; backup retention is separate. You cannot
        delete a review or edit its saved checklist here.
      </p>
      <p>
        You can run each review up to four times. Saving more information does
        not start the agent. Choose Review again to check your checklist against
        all the documents and information added so far. Each run is a new check,
        not a continuation of Chat.
      </p>
      <p>
        Requirements and proposal review is in preview and uses the same
        application-checking agent. It cannot fetch documents or change a
        business system.
      </p>
    </details>
  )
}
