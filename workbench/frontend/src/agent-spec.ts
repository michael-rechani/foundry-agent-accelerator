// The agent spec the Agent designer can end a conversation with. The model
// writes it as a fenced `agent-spec` JSON block after its plain-language
// summary; the browser reads it, hides the raw block, and offers a download.
// Nothing is created or stored in the Lab. Uses erasable TypeScript only so
// `node --test` can import it directly.

import { clip, modelPlaceholder } from './foundry-handoff.ts'

export type AgentSpec = {
  name: string
  summary: string
  instructions: string
  inputs: string
  outputs: string
  tools_needed: string[]
  human_decision: string
  // A catalog template the spec resembles, or null when none fits.
  closest_template: string | null
}

const block = /```agent-spec[ \t]*\r?\n([\s\S]*?)```/g
const maxText = 4000
const maxTools = 10

const text = (value: unknown, limit = maxText) =>
  typeof value === 'string' ? [...value.trim()].slice(0, limit).join('') : ''

export function validateSpec(value: unknown): AgentSpec | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const raw = value as Record<string, unknown>
  const name = text(raw.name, 80)
  const summary = text(raw.summary, 500)
  const instructions = text(raw.instructions)
  const humanDecision = text(raw.human_decision, 500)
  if (!name || !summary || !instructions || !humanDecision) return null
  const tools = Array.isArray(raw.tools_needed)
    ? raw.tools_needed
        .map((tool) => text(tool, 80))
        .filter(Boolean)
        .slice(0, maxTools)
    : []
  const closest = text(raw.closest_template, 80)
  return {
    name,
    summary,
    instructions,
    inputs: text(raw.inputs, 500),
    outputs: text(raw.outputs, 500),
    tools_needed: tools,
    human_decision: humanDecision,
    closest_template: closest || null,
  }
}

// Splits a designer reply into the text to show and the last valid spec in it.
// Every spec block is hidden, valid or not, so a malformed block never shows
// as raw JSON.
export function parseAgentSpec(reply: string): {
  text: string
  spec: AgentSpec | null
} {
  let spec: AgentSpec | null = null
  for (const match of reply.matchAll(block)) {
    try {
      spec = validateSpec(JSON.parse(match[1])) ?? spec
    } catch {
      // A block that isn't JSON is hidden and ignored.
    }
  }
  return { text: reply.replace(block, '').trim(), spec }
}

export const specSlug = (spec: Pick<AgentSpec, 'name'>) =>
  spec.name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48) || 'agent'

export const specFileName = (spec: Pick<AgentSpec, 'name'>) =>
  `${specSlug(spec)}.foundry-agent.json`

// The body of Foundry's "create agent version" request for a prompt agent, in
// the same shape as the library's agent definition, with a placeholder for
// your own model deployment.
export function specDefinition(spec: AgentSpec) {
  const metadata: Record<string, string> = {
    source: 'Foundry Agent Lab Agent designer',
    who_decides: clip(spec.human_decision),
  }
  if (spec.inputs) metadata.inputs = clip(spec.inputs)
  if (spec.outputs) metadata.outputs = clip(spec.outputs)
  if (spec.tools_needed.length)
    metadata.tools_to_connect = clip(spec.tools_needed.join(', '))
  if (spec.closest_template)
    metadata.closest_library_agent = clip(spec.closest_template)
  return {
    description: clip(spec.summary),
    definition: {
      kind: 'prompt',
      model: modelPlaceholder,
      instructions: spec.instructions,
      tools: [] as unknown[],
    },
    metadata,
  }
}
