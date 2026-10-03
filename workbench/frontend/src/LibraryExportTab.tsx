import { ArrowRight, Download, RefreshCw } from 'lucide-react'
import { creationRequest } from './agent-creation-client'
import {
  agentDefinition,
  definitionFileName,
  evaluationFileName,
  evaluationLines,
} from './foundry-handoff'
import { foundryAgentUrl } from './foundry-links'
import { FoundryLink } from './FoundryLink'
import type { LibraryTemplate } from './library-catalog'
import { creationNote, type ReadyAgent } from './library-helpers'
import { saveFile } from './save-file'
import type { ScorecardsState } from './scorecards-client'
import type { CreationCapability } from './workspace-config'

export function LibraryExportTab({
  template,
  scorecards,
  capability,
  foundryPortal,
  ready,
  busy,
  onCreate,
  onNotice,
}: {
  template: LibraryTemplate
  scorecards: ScorecardsState
  capability?: CreationCapability
  foundryPortal?: string | null
  ready?: ReadyAgent
  busy: boolean
  onCreate: () => void
  onNotice: (text: string) => void
}) {
  const testCases = scorecards.scorecards?.scorecards.find(
    (card) => card.template_id === template.id,
  )?.cases

  async function downloadRecord(id: string) {
    try {
      const record = await creationRequest(`agents/${id}`)
      saveFile(
        `${template.id}-record.json`,
        JSON.stringify(record, null, 2),
        'application/json',
      )
      onNotice('Saved record downloaded. Use it with the export command below.')
    } catch (problem) {
      onNotice(
        problem instanceof Error
          ? problem.message
          : 'The saved record could not be downloaded.',
      )
    }
  }

  function downloadDefinition() {
    saveFile(
      definitionFileName(template.id),
      JSON.stringify(agentDefinition(template), null, 2) + '\n',
      'application/json',
    )
    onNotice('Agent definition downloaded.')
  }

  function downloadTestCases() {
    if (!testCases) return
    saveFile(
      evaluationFileName(template.id),
      evaluationLines(testCases),
      'application/x-ndjson',
    )
    onNotice('Test requests downloaded.')
  }

  return (
    <div className="library-columns">
      <div className="library-stack">
        <section className="library-panel">
          <h2>Start in your Foundry project</h2>
          <p>
            Download the setup and the test requests, then use them in a Foundry
            project you control. Nothing is created until you do.
          </p>
          <div className="library-download">
            <button
              type="button"
              className="library-secondary"
              onClick={downloadDefinition}
            >
              <Download size={16} /> Download agent definition
            </button>
            <p className="library-muted">
              Instructions and settings for a Foundry prompt agent. Add your own
              model deployment.
            </p>
          </div>
          <div className="library-download">
            {testCases ? (
              <>
                <button
                  type="button"
                  className="library-secondary"
                  onClick={downloadTestCases}
                >
                  <Download size={16} /> Download test requests
                </button>
                <p className="library-muted">
                  {testCases.length} requests for a Foundry evaluation, each
                  with what a good answer shows.
                </p>
              </>
            ) : scorecards.error ? (
              <>
                <p className="library-muted">The test requests did not load.</p>
                <button
                  type="button"
                  className="library-secondary"
                  onClick={scorecards.retry}
                >
                  <RefreshCw size={14} /> Try again
                </button>
              </>
            ) : scorecards.scorecards ? (
              <p className="library-muted">
                This agent has no test requests yet.
              </p>
            ) : (
              <p className="library-muted" role="status">
                Checking for test requests...
              </p>
            )}
          </div>
        </section>
        <section className="library-panel">
          <h2>Or get the full hosted-agent package</h2>
          <p>{template.export.description}</p>
          <p className="library-muted hood-only">
            Format {template.export.package_format}. Target: a Microsoft Foundry
            hosted agent in a project you control.
          </p>
          {!template.export.exportable ? (
            <p className="library-muted">
              Export is not available for this agent yet.
            </p>
          ) : ready ? (
            <button
              type="button"
              className="library-primary"
              onClick={() => void downloadRecord(ready.recordId)}
            >
              <Download size={16} /> Download saved record
            </button>
          ) : (
            <>
              <button
                type="button"
                className="library-primary"
                disabled={!capability || busy}
                onClick={onCreate}
              >
                Create this agent to get the package <ArrowRight size={16} />
              </button>
              <p className="library-muted">
                {capability
                  ? 'Opens Create agent with this template. Nothing is created until you confirm on the last step.'
                  : creationNote(capability)}
              </p>
            </>
          )}
          {ready && foundryPortal && (
            <p className="library-muted hood-only">
              <FoundryLink
                href={foundryAgentUrl(foundryPortal, ready.agent.agent)}
              >
                Open this agent in Foundry
              </FoundryLink>
            </p>
          )}
        </section>
      </div>
      <section className="library-panel">
        <h2>Set it up in your Foundry project</h2>
        <ol className="library-steps">
          <li>Provide a model deployment in your own Foundry project.</li>
          <li>
            Create a prompt agent from the definition file, or paste its
            instructions into the agent builder.
          </li>
          <li>
            Review the instructions, limits and acceptance cases with your
            policy owners.
          </li>
          {template.tool_mode.id !== 'none' && (
            <li>
              Replace the sample lookups with reviewed connectors to your own
              systems.
            </li>
          )}
          {testCases && (
            <li>
              Run the test requests as a Foundry evaluation and read each answer
              against what a good answer shows.
            </li>
          )}
          <li className="hood-only">
            Build and check the bundle from the saved record:
          </li>
        </ol>
        <pre className="library-sample library-command hood-only">
          {`python hosted-agents/bundle.py export-created --record ${template.id}-record.json --output ${template.id}.agent-bundle.zip
python hosted-agents/bundle.py inspect ${template.id}.agent-bundle.zip
python hosted-agents/bundle.py deploy ${template.id}.agent-bundle.zip --endpoint <your-project-endpoint> --model <your-deployment> --agent-name <your-agent-name>`}
        </pre>
        <p className="library-muted">
          There is no one-click cross-environment deployment. Deploying creates
          a billable hosted version in your project; your team runs it with its
          own credentials.
        </p>
      </section>
    </div>
  )
}
