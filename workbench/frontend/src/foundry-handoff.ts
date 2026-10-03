// Files a builder can take into their own Foundry project, built in the browser
// from what the Lab already serves. Nothing is created or stored in the Lab.
// Uses erasable TypeScript only so `node --test` can import it directly.

import type { LibraryTemplate } from './library-catalog'
import type { ScorecardCase } from './scorecards'

export const modelPlaceholder = '<your-model-deployment>'
// Foundry allows up to 512 characters per metadata value.
const metadataLimit = 512

function clip(value: string) {
  const letters = [...value]
  return letters.length > metadataLimit
    ? letters.slice(0, metadataLimit - 1).join('') + '…'
    : value
}

// The body of Foundry's "create agent version" request for a prompt agent. The
// agent name goes in the request path, so the file name carries it instead.
export function agentDefinition(
  template: Pick<
    LibraryTemplate,
    'id' | 'summary' | 'instructions' | 'human_decision' | 'tools'
  >,
) {
  const metadata: Record<string, string> = {
    source: 'Foundry Agent Lab agent library',
    library_agent: template.id,
    who_decides: clip(template.human_decision),
  }
  if (template.tools.length)
    metadata.tools_to_connect = clip(
      template.tools.map((tool) => tool.name).join(', '),
    )
  return {
    description: clip(template.summary),
    definition: {
      kind: 'prompt',
      model: modelPlaceholder,
      instructions: template.instructions,
      tools: [] as unknown[],
    },
    metadata,
  }
}

export const definitionFileName = (templateId: string) =>
  `${templateId}.foundry-agent.json`

// One line per test request, in the shape Foundry evaluations take when
// Foundry generates the answers itself: the request goes in `query`. The other
// columns describe the case for the person reading the results.
export function evaluationLines(
  cases: Pick<ScorecardCase, 'id' | 'category' | 'goal' | 'input'>[],
) {
  return (
    cases
      .map((item) =>
        JSON.stringify({
          query: item.input,
          case_id: item.id,
          category: item.category,
          expected_behavior: item.goal,
        }),
      )
      .join('\n') + '\n'
  )
}

export const evaluationFileName = (templateId: string) =>
  `${templateId}.foundry-test-cases.jsonl`
