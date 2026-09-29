import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { plainStep, receiptState, stepsSummary } from '../src/answer-steps.ts'
import type { Receipt, Turn } from '../src/conversation-types.ts'

const receipt = (tool: string, agent: string | null, verified = true) =>
  ({ tool, call_id: 'call', verified, agent, output: null }) as Receipt

const turn = (receipts: Receipt[], stored = false): Turn => ({
  question: 'Check this',
  stored,
  result: {
    request_id: 'request',
    agent: 'invoice-reviewer-1a2b',
    text: 'Answer',
    receipts,
    elapsed_ms: 1200,
  },
})

describe('answer steps', () => {
  it('describes lookups from the recorded tool name only', () => {
    const current = turn([])
    assert.equal(
      plainStep(
        current,
        receipt('lookup_purchase_order', 'invoice-reviewer-1a2b'),
      ),
      'Looked up the purchase order',
    )
    assert.equal(
      plainStep(current, receipt('lookup_demo_request', null)),
      'Looked up the request',
    )
    assert.equal(
      plainStep(current, receipt('inspect_case', null)),
      'Checked the case',
    )
    assert.equal(
      plainStep(current, receipt('summarize', null)),
      'Used summarize',
    )
  })

  it('names another agent with its Lab label when one is known', () => {
    const current = turn([])
    const handoff = receipt('inspect_application', 'application-review-agent')
    assert.equal(
      plainStep(current, handoff, {
        'application-review-agent': 'Checklist reviewer',
      }),
      'Asked the Checklist reviewer',
    )
    assert.equal(
      plainStep(current, handoff),
      'Asked the Application review agent',
    )
  })

  it('summarizes what was recorded without inventing steps', () => {
    assert.equal(stepsSummary(turn([])), 'No lookups or other agents recorded')
    assert.equal(
      stepsSummary(
        turn([
          receipt('lookup_purchase_order', 'invoice-reviewer-1a2b'),
          receipt('lookup_delivery_record', 'invoice-reviewer-1a2b'),
        ]),
      ),
      'Used 2 lookups',
    )
    assert.equal(
      stepsSummary(
        turn([
          receipt('inspect_application', 'application-review-agent'),
          receipt('lookup_purchase_order', null),
        ]),
      ),
      'Asked another agent and used 1 lookup',
    )
  })

  it('never marks stored steps as live-confirmed', () => {
    const item = receipt('lookup_purchase_order', null)
    assert.equal(receiptState(turn([item]), item), 'verified')
    assert.equal(receiptState(turn([item], true), item), 'stored')
    const unverified = receipt('lookup_purchase_order', null, false)
    assert.equal(receiptState(turn([unverified]), unverified), 'unverified')
  })
})
