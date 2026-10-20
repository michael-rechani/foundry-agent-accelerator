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

// A tester's verdict on one answer. It is saved to shared history with the
// conversation, and is included in the exported file.
export type Rating = { value: 'up' | 'down'; reason?: string }

export type Turn = {
  question: string
  result: Result
  stored?: boolean
  rating?: Rating
  // Earlier answers to this same question, oldest first, kept after "Try
  // again". Like a rating, they live only in this tab and the exported file.
  earlier?: Result[]
}
