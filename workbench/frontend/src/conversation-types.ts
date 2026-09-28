import type { Usage } from './token-usage'

export type Receipt = {
  tool: string
  call_id: string | null
  verified: boolean
  agent: string | null
  output: string | null
}

export type Result = {
  request_id: string
  agent: string
  text: string
  receipts: Receipt[]
  elapsed_ms: number
  // Absent on replies saved before token reporting; null when the service reported none.
  usage?: Usage | null
}

export type Turn = { question: string; result: Result; stored?: boolean }
