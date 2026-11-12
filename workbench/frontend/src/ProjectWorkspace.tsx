import { ArrowRight, Download, FolderOpen, Plus } from 'lucide-react'
import type { Agent } from './workspace-config'
import { projectFields, type ProjectBrief } from './project-brief'
import type { ProjectBriefs } from './use-project-briefs'
import { useUnsavedWarning } from './use-chat-effects'
import { saveFile } from './save-file'
import './projects.css'

export function ProjectWorkspace({
  state,
  active,
  agents,
  busy,
  designerAvailable,
  currentWork,
  onDesign,
  onDemonstrate,
  onChat,
  onLibrary,
  onAddOns,
}: {
  state: ProjectBriefs
  active: boolean
  agents: Agent[]
  busy: boolean
  designerAvailable: boolean
  currentWork?: { turns: number; specName?: string }
  onDesign: (project: ProjectBrief) => void
  onDemonstrate: (project: ProjectBrief) => void
  onChat: () => void
  onLibrary: () => void
  onAddOns: () => void
}) {
  return (
    <main className="project-workspace" hidden={!active}>
      <header className="project-heading">
        <div>
          <h1>Projects</h1>
          <p>
            Keep the purpose in view. Build, try and demonstrate an agent using
            the Lab&apos;s existing tools.
          </p>
        </div>
        <FolderOpen size={28} aria-hidden="true" />
      </header>
      <p className="project-boundary">
        <strong>Briefs are saved only in this browser.</strong> Not synced,
        backed up or isolated by sign-in. Anyone using this browser profile can
        read them; clearing browser data removes them. Use fictional data, never
        secrets or customer records. Chats, draft tests and agents are not saved
        in the project.
      </p>
      {state.error && (
        <p className="creation-error" role="alert">
          {state.error}
        </p>
      )}
      {state.conflict && (
        <button
          className="creation-secondary"
          disabled={state.writing}
          onClick={() => state.reload()}
        >
          Reload saved projects
        </button>
      )}
      {state.readBlocked ? (
        <button
          className="creation-secondary"
          disabled={state.writing}
          onClick={() => {
            if (
              window.confirm(
                'Forget all project briefs stored in this browser? This cannot be undone. It does not delete any shared chats or agents.',
              )
            )
              void state.forget()
          }}
        >
          Forget local projects
        </button>
      ) : (
        <ProjectEditor
          state={state}
          agents={agents}
          busy={busy}
          designerAvailable={designerAvailable}
          currentWork={currentWork}
          onDesign={onDesign}
          onDemonstrate={onDemonstrate}
          onChat={onChat}
          onLibrary={onLibrary}
          onAddOns={onAddOns}
        />
      )}
    </main>
  )
}

function ProjectEditor({
  state,
  agents,
  busy,
  designerAvailable,
  currentWork,
  onDesign,
  onDemonstrate,
  onChat,
  onLibrary,
  onAddOns,
}: Omit<Parameters<typeof ProjectWorkspace>[0], 'active'>) {
  const project = state.selected
  const { text, dirty, saved } = state
  useUnsavedWarning(dirty)
  const ready = !!project && !dirty && !state.writing
  const selectedAgent = agents.find((agent) => agent.id === text.agentId)
  function choose(id: string) {
    state.select(id)
  }
  return (
    <>
      <div className="project-toolbar">
        <label htmlFor="project-picker">Project</label>
        <select
          id="project-picker"
          value={state.selectedId}
          disabled={state.writing}
          onChange={(event) => choose(event.target.value)}
        >
          <option value="">New project brief</option>
          {state.projects.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <button
          className="creation-secondary"
          onClick={() => choose('')}
          disabled={!project || state.writing}
        >
          <Plus size={16} aria-hidden="true" />
          New project
        </button>
      </div>
      <div className="project-columns">
        <section
          className="project-brief"
          aria-labelledby="project-brief-title"
        >
          <h2 id="project-brief-title">
            {project ? 'Project brief' : 'Start with the job to be done'}
          </h2>
          <p>
            Write a goal and what a good result would show. Notes are not agent
            instructions until you choose to load them into the designer.
          </p>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void state.save()
            }}
          >
            {Object.entries(projectFields).map(([field, { label, limit }]) => {
              const key = field as keyof typeof projectFields
              return (
                <div className="project-field" key={field}>
                  <label htmlFor={`project-${field}`}>
                    {label}
                    {key === 'name' || key === 'goal' ? ' (required)' : ''}
                  </label>
                  {key === 'name' ? (
                    <input
                      id={`project-${field}`}
                      required
                      disabled={state.writing}
                      maxLength={limit}
                      value={text[key]}
                      onChange={(event) => {
                        state.edit(key, event.target.value)
                      }}
                    />
                  ) : (
                    <textarea
                      id={`project-${field}`}
                      rows={key === 'goal' ? 3 : 2}
                      required={key === 'goal'}
                      disabled={state.writing}
                      maxLength={limit}
                      value={text[key]}
                      onChange={(event) => {
                        state.edit(key, event.target.value)
                      }}
                    />
                  )}
                </div>
              )
            })}
            <div className="project-field">
              <label htmlFor="project-agent">Agent for demonstration</label>
              <select
                id="project-agent"
                value={text.agentId}
                disabled={state.writing}
                onChange={(event) => {
                  state.edit('agentId', event.target.value)
                }}
              >
                <option value="">Choose an available agent</option>
                {text.agentId && !selectedAgent && (
                  <option value={text.agentId}>
                    Previously chosen agent (unavailable)
                  </option>
                )}
                {agents.map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.label} - {agent.category}
                  </option>
                ))}
              </select>
            </div>
            <div className="project-actions">
              <button
                className="creation-primary"
                type="submit"
                disabled={
                  state.writing ||
                  !dirty ||
                  !text.name.trim() ||
                  !text.goal.trim()
                }
              >
                Save brief in this browser
              </button>
              <span role="status">
                {state.writing
                  ? 'Saving local projects...'
                  : dirty
                    ? 'Unsaved edits'
                    : saved
                      ? 'Saved in this browser.'
                      : project
                        ? 'Loaded from this browser.'
                        : 'Nothing saved yet.'}
              </span>
            </div>
          </form>
          {project && (
            <div className="project-actions">
              <button
                className="creation-secondary"
                disabled={dirty || state.writing}
                onClick={() =>
                  saveFile(
                    `${project.name.replace(/[^a-zA-Z0-9-]/g, '-').slice(0, 60) || 'project'}.project-brief.json`,
                    JSON.stringify(
                      {
                        version: 1,
                        storage:
                          'browser-local brief only; no chats, tests or runtime',
                        project,
                      },
                      null,
                      2,
                    ) + '\n',
                    'application/json',
                  )
                }
              >
                <Download size={16} aria-hidden="true" />
                Export saved brief
              </button>
              <button
                className="creation-secondary"
                disabled={state.writing}
                onClick={() => {
                  if (
                    window.confirm(
                      `Delete the local brief "${project.name}"${dirty ? ' and unsaved edits' : ''}? Shared chats and agents will not be deleted.`,
                    )
                  )
                    void state.remove()
                }}
              >
                Delete local brief
              </button>
            </div>
          )}
        </section>
        <section
          className="project-journey"
          aria-labelledby="project-journey-title"
        >
          <h2 id="project-journey-title">From brief to demonstration</h2>
          <p>
            Save your brief before using it below. Each action opens real Lab
            functionality; nothing runs automatically.
          </p>
          <ol>
            <li>
              <h3>Describe and build</h3>
              <p>
                Load the goal, context, decisions and deliverable notes into
                Agent designer. Review the message before sending it to the
                model.
              </p>
              <button
                className="creation-primary"
                disabled={!ready || busy || !designerAvailable}
                onClick={() => project && onDesign(project)}
              >
                Load brief in designer
                <ArrowRight size={16} aria-hidden="true" />
              </button>
              {!designerAvailable && (
                <p className="project-note">
                  Agent designer needs library previews enabled in a connected
                  Lab. Local brief saving and library browsing still work.
                </p>
              )}
            </li>
            <li>
              <h3>Try the draft and inspect evidence</h3>
              <p>
                In the designer&apos;s spec card, use{' '}
                <strong>Test this draft first</strong>, review actual answers
                and accept or reject instruction changes. Tests need a supported
                template and explicit model-cost consent. Download the spec and
                test report there.
              </p>
              {currentWork ? (
                <>
                  <p className="project-session" role="status">
                    This session: {currentWork.turns} completed chat{' '}
                    {currentWork.turns === 1 ? 'turn' : 'turns'}.
                    {currentWork.specName
                      ? ` Spec received: ${currentWork.specName}. Not proof of a passing test or a deployed agent.`
                      : ' No designer spec in the current conversation yet.'}
                  </p>
                  <button className="creation-secondary" onClick={onChat}>
                    Return to current work
                    <ArrowRight size={16} aria-hidden="true" />
                  </button>
                </>
              ) : (
                <p className="project-note">
                  No project conversation linked in this page session. Chats and
                  draft test state are not restored by the saved brief.
                </p>
              )}
              <p className="project-note">
                Template publication remains operator- and cost-gated. Custom
                tools and customer systems are not connected by a brief or spec.
              </p>
            </li>
            <li>
              <h3>Prompt and demonstrate</h3>
              <p>
                Choose an available agent and save a fictional sample prompt in
                the brief. Open it in Chat, send it when ready, then use
                Chat&apos;s presentation control. Selecting an agent does not
                configure it from this brief.
              </p>
              <button
                className="creation-secondary"
                disabled={
                  !ready ||
                  busy ||
                  !selectedAgent ||
                  !project?.demoPrompt.trim()
                }
                onClick={() => project && onDemonstrate(project)}
              >
                Open demonstration chat
                <ArrowRight size={16} aria-hidden="true" />
              </button>
              {text.agentId && !selectedAgent && (
                <p className="project-note">
                  The saved agent is unavailable or no longer ready. Choose
                  another available agent; the brief is preserved.
                </p>
              )}
            </li>
          </ol>
          <div className="project-capabilities">
            <h3>Reuse what exists</h3>
            <p>
              Find a template, try its sample, or inspect optional capabilities
              before adding scope.
            </p>
            <div className="project-actions">
              <button className="creation-secondary" onClick={onLibrary}>
                Browse agent library
              </button>
              <button className="creation-secondary" onClick={onAddOns}>
                Explore add-ons
              </button>
            </div>
          </div>
          <p className="project-note">
            The Lab has no per-user authorization. Explicitly saved shared chats
            and created agents remain visible to everyone with Lab access. This
            project is not a security boundary.
          </p>
        </section>
      </div>
    </>
  )
}
