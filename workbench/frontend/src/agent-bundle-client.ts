// The browser side of "Download ready-to-deploy agent". The Lab builds the file
// from the Agent designer's spec without a model call and stores nothing; the
// person checks it with bundle.py and deploys it to their own Foundry project.
// Uses erasable TypeScript only so `node --test` can import it directly.

import { specSlug, type AgentSpec } from './agent-spec.ts'
import {
  failureFromProblem,
  failureFromResponse,
  makeFailure,
  type ChatFailure,
} from './chat-failure.ts'
import { errorBody, readJson } from './request.ts'

const messages: Record<string, string> = {
  invalid_bundle:
    "The Lab couldn't build this file because the spec's instructions are too short. Ask the designer to add more detail, then try again.",
  library_preview_disabled:
    "Library previews are turned off in this Lab, so it can't build this file.",
}
const timeoutMessage =
  'Building the file took too long. Nothing was sent to Foundry. Try again.'
const unreadableMessage = "The Lab didn't send back a file. Try again."
// The Lab refuses a longer description. The summary is one sentence, so this only trims a stray long one.
const maxDescription = 500

export class BundleError extends Error {
  readonly failure: ChatFailure

  constructor(failure: ChatFailure) {
    super(failure.message)
    this.failure = failure
  }
}

export const bundleFileName = (spec: Pick<AgentSpec, 'name'>) =>
  `${specSlug(spec)}.agent-bundle.zip`

// The same words as the "Download agent spec" file, so both carry one design.
export const bundleRequest = (spec: AgentSpec) => ({
  name: specSlug(spec),
  description: [...spec.summary].slice(0, maxDescription).join(''),
  instructions: spec.instructions,
})

function describeFailure(response: Response, data: unknown) {
  const failure = failureFromResponse(response, data)
  const message = messages[errorBody(data).error ?? '']
  return message
    ? makeFailure(message, {
        reference: failure.reference,
        status: response.status,
      })
    : failure
}

export async function fetchBundle(
  spec: AgentSpec,
  timeoutMs = 20_000,
): Promise<Blob> {
  try {
    const response = await fetch('/api/agent-bundles', {
      method: 'POST',
      headers: {
        'X-Workbench-Request': '1',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(bundleRequest(spec)),
      signal: AbortSignal.timeout(timeoutMs),
    })
    if (!response.ok)
      throw new BundleError(describeFailure(response, await readJson(response)))
    // A proxy can answer 200 with a page of its own; only a zip is a bundle.
    if (!response.headers.get('Content-Type')?.startsWith('application/zip'))
      throw new BundleError(makeFailure(unreadableMessage))
    return await response.blob()
  } catch (problem) {
    if (problem instanceof BundleError) throw problem
    if (
      problem instanceof DOMException &&
      (problem.name === 'TimeoutError' || problem.name === 'AbortError')
    )
      throw new BundleError(makeFailure(timeoutMessage))
    throw new BundleError(failureFromProblem(problem))
  }
}
