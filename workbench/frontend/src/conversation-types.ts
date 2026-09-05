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
}

export type Turn = { question: string; result: Result; stored?: boolean }
