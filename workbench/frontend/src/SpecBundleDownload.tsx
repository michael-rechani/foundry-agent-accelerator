import { useState } from 'react'
import { Archive, LoaderCircle } from 'lucide-react'
import { BundleError, bundleFileName, fetchBundle } from './agent-bundle-client'
import type { AgentSpec } from './agent-spec'
import { failureFromProblem, type ChatFailure } from './chat-failure'
import { saveFile } from './save-file'

// Builds a ready-to-deploy file from the spec on the Lab's side, with no model
// call, and saves it to the person's computer. Nothing is published or stored:
// the person checks the file and deploys it to their own Foundry project.
export function SpecBundleDownload({ spec }: { spec: AgentSpec }) {
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<ChatFailure | null>(null)

  async function download() {
    if (busy) return
    setBusy(true)
    setFailure(null)
    try {
      saveFile(bundleFileName(spec), await fetchBundle(spec), 'application/zip')
    } catch (problem) {
      setFailure(
        problem instanceof BundleError
          ? problem.failure
          : failureFromProblem(problem),
      )
    } finally {
      setBusy(false)
    }
  }

  const file = bundleFileName(spec)
  return (
    <div className="spec-bundle">
      <div className="agent-spec-actions">
        <button
          type="button"
          className="library-secondary"
          disabled={busy}
          onClick={() => void download()}
        >
          {busy ? (
            <LoaderCircle size={16} className="spin" aria-hidden="true" />
          ) : (
            <Archive size={16} aria-hidden="true" />
          )}
          Download ready-to-deploy agent
        </button>
      </div>
      {failure && (
        <p className="spec-build-error" role="alert">
          {failure.message}
          {failure.reference && (
            <>
              {' '}
              Reference: <code>{failure.reference}</code>
            </>
          )}
        </p>
      )}
      <p className="agent-spec-note">
        A file you can deploy to your own Foundry project. The agent follows
        this spec&apos;s instructions, like a plain chat assistant. It
        can&apos;t look anything up or read documents, and it doesn&apos;t have
        the Lab&apos;s built-in safety rules. Check it over before you use it.
        Nothing is sent to Foundry from here.
      </p>
      <pre className="library-sample library-command hood-only">
        {`python hosted-agents/bundle.py inspect ${file}
python hosted-agents/bundle.py deploy ${file} --endpoint <your-project-endpoint> --model <your-deployment> --agent-name <your-agent-name>`}
      </pre>
    </div>
  )
}
