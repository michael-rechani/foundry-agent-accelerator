import type { Dispatch, SetStateAction } from 'react'
import { CheckCheck, FileText, Plus, Trash2 } from 'lucide-react'
import type { Source } from './review-client'

export function ReviewForm({
  title,
  criteria,
  sources,
  agentLabel,
  busy,
  enabled,
  retentionDays,
  onTitle,
  onCriteria,
  onSources,
  onSample,
  onSubmit,
}: {
  title: string
  criteria: string
  sources: Source[]
  agentLabel?: string
  busy: boolean
  enabled: boolean
  retentionDays: number
  onTitle: (value: string) => void
  onCriteria: (value: string) => void
  onSources: Dispatch<SetStateAction<Source[]>>
  onSample: () => void
  onSubmit: () => void
}) {
  return (
    <form
      className="review-form"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit()
      }}
    >
      <div className="review-form-bar">
        <div>
          <strong>
            Agent doing this check:{' '}
            {agentLabel || 'Agent unavailable in this catalog'}
          </strong>
          <p className="review-hint">
            Uses the Lab&apos;s default agent, not your Chat selection. No new
            agent is created.
          </p>
        </div>
        <button
          type="button"
          className="review-secondary"
          onClick={onSample}
          disabled={busy}
        >
          <FileText size={16} />
          Use fictional example
        </button>
      </div>
      <p className="review-hint" id="review-input-guide">
        Paste made-up text directly; file uploads and fetching links are not
        available. Add up to 12 checklist items (1,000 characters each) and 12
        documents (12,000 characters each), within 30,000 content characters in
        total.
      </p>
      <label>
        Review title
        <input
          required
          aria-describedby="review-privacy"
          maxLength={80}
          value={title}
          onChange={(event) => onTitle(event.target.value)}
        />
      </label>
      <label>
        Checklist, one item per line
        <textarea
          required
          rows={4}
          maxLength={12000}
          aria-describedby="review-input-guide review-privacy"
          placeholder="For example: Include a project budget."
          value={criteria}
          onChange={(event) => onCriteria(event.target.value)}
        />
      </label>
      <h2>Documents to check</h2>
      {sources.map((item, index) => (
        <div className="source-editor" key={item.id}>
          <label>
            Document {item.id.slice(4)}
            <textarea
              required
              rows={5}
              maxLength={12000}
              aria-describedby="review-input-guide review-privacy"
              placeholder="Paste a document or note here. Results will point back to this text."
              value={item.text}
              onChange={(event) =>
                onSources((previous) =>
                  previous.map((source, position) =>
                    position === index
                      ? { ...source, text: event.target.value }
                      : source,
                  ),
                )
              }
            />
          </label>
          <button
            type="button"
            className="review-icon"
            aria-label={`Remove document ${item.id.slice(4)}`}
            title={`Remove document ${item.id.slice(4)}`}
            disabled={sources.length === 1 || busy}
            onClick={() =>
              onSources((previous) =>
                previous.filter((source) => source.id !== item.id),
              )
            }
          >
            <Trash2 size={16} />
          </button>
        </div>
      ))}
      <p className="review-hint" id="review-privacy">
        Use fictional data only, never personal or confidential information.{' '}
        {enabled
          ? `Create shared review saves this checklist and text for everyone who can open the Lab. Reviews expire ${retentionDays} days after the last update; backup retention is separate. It does not run the agent; choose Run review next.`
          : 'Saving and running reviews are unavailable here.'}
      </p>
      <footer>
        <button
          type="button"
          className="review-secondary"
          disabled={sources.length >= 12 || busy}
          onClick={() =>
            onSources((previous) => [
              ...previous,
              {
                id: `SRC-${Math.max(...previous.map((item) => Number(item.id.slice(4)))) + 1}`,
                text: '',
              },
            ])
          }
        >
          <Plus size={16} />
          Add document
        </button>
        <button
          className="review-primary"
          aria-describedby="review-privacy"
          disabled={!enabled || busy}
        >
          <CheckCheck size={16} />
          Create shared review
        </button>
      </footer>
    </form>
  )
}
