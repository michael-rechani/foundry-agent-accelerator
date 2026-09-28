import type { Receipt, Turn } from './conversation-types'

export type ReceiptState = 'verified' | 'unverified' | 'stored'

// Stored history is never reverified, so it can't claim live verification.
export function receiptState(turn: Turn, receipt: Receipt): ReceiptState {
  if (turn.stored) return 'stored'
  return receipt.verified ? 'verified' : 'unverified'
}

// A receipt is a handoff only when it names another agent. Created agents
// bind simulated lookups to their own runtime name; those are tool calls.
export function isHandoff(turn: Turn, receipt: Receipt) {
  return Boolean(receipt.agent) && receipt.agent !== turn.result.agent
}

function words(name: string) {
  return name
    .replace(/-[0-9a-f]{4,}$/i, '')
    .split(/[_\-\s]+/)
    .filter((word) => word && word.toLowerCase() !== 'demo')
    .map((word) => word.toLowerCase())
}

const lookupVerbs = new Set([
  'lookup',
  'get',
  'read',
  'fetch',
  'search',
  'find',
])
const checkVerbs = new Set(['check', 'inspect', 'review', 'verify'])

// Plain wording is derived only from the recorded tool or agent name.
export function plainStep(
  turn: Turn,
  receipt: Receipt,
  agentLabels: Record<string, string> = {},
) {
  if (isHandoff(turn, receipt)) {
    const agent = receipt.agent as string
    const name = agentLabels[agent]
    if (name) return `Asked the ${name}`
    const text = words(agent).join(' ')
    return `Asked the ${text.charAt(0).toUpperCase()}${text.slice(1)}`
  }
  const [verb, ...rest] = words(receipt.tool)
  const object = rest.join(' ')
  if (verb && object && lookupVerbs.has(verb)) return `Looked up the ${object}`
  if (verb && object && checkVerbs.has(verb)) return `Checked the ${object}`
  return `Used ${[verb, ...rest].join(' ')}`
}

export function stepsSummary(turn: Turn) {
  const handoffs = turn.result.receipts.filter((receipt) =>
    isHandoff(turn, receipt),
  ).length
  const tools = turn.result.receipts.length - handoffs
  const parts = []
  if (handoffs)
    parts.push(
      handoffs === 1 ? 'asked another agent' : `asked ${handoffs} other agents`,
    )
  if (tools) parts.push(tools === 1 ? 'used 1 lookup' : `used ${tools} lookups`)
  if (!parts.length) return 'No lookups or other agents recorded'
  const text = parts.join(' and ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}
