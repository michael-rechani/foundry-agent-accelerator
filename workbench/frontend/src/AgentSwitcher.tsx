import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import {
  Check,
  ChevronDown,
  Construction,
  LibraryBig,
  Search,
} from 'lucide-react'
import type { Agent } from './workspace-config'

export type SwitcherOption = {
  agent: Agent
  detail: string
  inProgress?: boolean
}

export function AgentSwitcher({
  label,
  selected,
  ready,
  previews,
  previewNote,
  disabled,
  onChoose,
  onBrowse,
}: {
  label: string
  selected: string
  ready: SwitcherOption[]
  previews: SwitcherOption[]
  previewNote: string
  disabled: boolean
  onChoose: (id: string) => void
  onBrowse: () => void
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const panel = useRef<HTMLDivElement>(null)
  const search = useRef<HTMLInputElement>(null)
  const panelId = useId()

  useEffect(() => {
    if (!open) return
    search.current?.focus()
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  const terms = query.toLowerCase().split(/\s+/).filter(Boolean)
  const visible = (options: SwitcherOption[]) =>
    options.filter(({ agent, detail }) => {
      const text = `${agent.label} ${detail} ${agent.description}`.toLowerCase()
      return terms.every((term) => text.includes(term))
    })
  const groups: [string, SwitcherOption[], string][] = [
    ['Ready agents', visible(ready), ''],
    ['Library previews', visible(previews), previewNote],
  ]
  const empty = groups.every(([, options]) => !options.length)

  function choose(id: string) {
    setOpen(false)
    setQuery('')
    trigger.current?.focus()
    onChoose(id)
  }

  // The panel is a dialog: Escape closes it and gives focus back to the
  // trigger, and Tab and Shift+Tab wrap inside it instead of leaving. The
  // wrapper only receives the keys that bubble up from the trigger and panel.
  function keyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (!open) return
    if (event.key === 'Escape') {
      event.stopPropagation()
      setOpen(false)
      trigger.current?.focus()
      return
    }
    if (event.key !== 'Tab' || !panel.current) return
    const stops = panel.current.querySelectorAll<HTMLElement>(
      'input:not(:disabled), button:not(:disabled)',
    )
    const first = stops[0]
    const last = stops[stops.length - 1]
    const active = document.activeElement
    const inside = active !== panel.current && panel.current.contains(active)
    if (event.shiftKey ? active === first || !inside : active === last) {
      event.preventDefault()
      const target = event.shiftKey ? last : first
      target.focus()
    }
  }

  return (
    <div
      className="agent-switcher"
      ref={root}
      role="presentation"
      onKeyDown={keyDown}
    >
      <button
        type="button"
        ref={trigger}
        className="agent-picker"
        title="Choose an agent"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="agent-name">{label}</span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {open && (
        <div
          className="agent-switcher-panel"
          id={panelId}
          ref={panel}
          role="dialog"
          aria-modal="true"
          aria-label="Choose an agent"
          tabIndex={-1}
        >
          <label className="agent-switcher-search">
            <Search size={15} aria-hidden="true" />
            <span className="visually-hidden">Search agents</span>
            <input
              ref={search}
              type="search"
              value={query}
              placeholder="Search agents"
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <div className="agent-switcher-groups">
            {groups.map(([title, options, note]) =>
              options.length || (note && !terms.length) ? (
                <section key={title} aria-label={title}>
                  <h2>{title}</h2>
                  {note && <p className="agent-switcher-note">{note}</p>}
                  <ul>
                    {options.map(({ agent, detail, inProgress }) => (
                      <li key={agent.id}>
                        <button
                          type="button"
                          aria-current={
                            agent.id === selected ? 'true' : undefined
                          }
                          onClick={() => choose(agent.id)}
                        >
                          <span>
                            <strong>
                              {agent.label}
                              {inProgress && (
                                <span
                                  className="progress-pill"
                                  title="Not yet validated live"
                                >
                                  <Construction size={11} aria-hidden="true" />
                                  In progress
                                </span>
                              )}
                            </strong>
                            <small>{detail}</small>
                          </span>
                          {agent.id === selected && (
                            <Check size={15} aria-label="Current agent" />
                          )}
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null,
            )}
            {empty && terms.length > 0 && (
              <p className="agent-switcher-note">No agents match “{query}”.</p>
            )}
          </div>
          <button
            type="button"
            className="agent-switcher-browse"
            onClick={() => {
              setOpen(false)
              onBrowse()
            }}
          >
            <LibraryBig size={15} aria-hidden="true" /> Browse the full library
          </button>
        </div>
      )}
    </div>
  )
}
