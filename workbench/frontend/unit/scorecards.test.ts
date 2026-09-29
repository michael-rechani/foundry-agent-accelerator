import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { describe, it } from 'node:test'
import {
  categoryTitles,
  formatCostPerAnswer,
  formatDate,
  parseScorecards,
} from '../src/scorecards.ts'

const raw = JSON.parse(
  await readFile(
    new URL('../../agent_scorecards.json', import.meta.url),
    'utf8',
  ),
)

describe('agent scorecards', () => {
  it('accepts the served scorecards and names every category plainly', () => {
    const { scorecards } = parseScorecards(raw)
    assert.ok(scorecards.length > 0)
    for (const card of scorecards)
      for (const item of card.cases) assert.ok(categoryTitles[item.category])
  })

  it('rejects a summary that disagrees with its cases', () => {
    const copy = structuredClone(raw)
    copy.scorecards[0].summary.passed += 1
    assert.throws(() => parseScorecards(copy), /could not be read/)
  })

  it('rejects a passed case that still has notes', () => {
    const copy = structuredClone(raw)
    const card = copy.scorecards[0]
    card.cases[0].passed = true
    card.cases[0].notes = ["missing 'item 1'"]
    card.summary.passed = card.cases.filter(
      (item: { passed: boolean }) => item.passed,
    ).length
    assert.throws(() => parseScorecards(copy), /could not be read/)
  })

  it('shows who signed off, and rejects a sign-off that names no one', () => {
    const signed = structuredClone(raw)
    Object.assign(signed.scorecards[0], {
      signed_off: true,
      signed_off_by: 'Pat Reviewer',
      signed_off_on: '2026-09-30',
    })
    assert.equal(
      parseScorecards(signed).scorecards[0].signed_off_by,
      'Pat Reviewer',
    )
    const anonymous = structuredClone(signed)
    anonymous.scorecards[0].signed_off_by = null
    assert.throws(() => parseScorecards(anonymous), /could not be read/)
    const stray = structuredClone(raw)
    stray.scorecards[0].signed_off_by = 'Pat Reviewer'
    assert.throws(() => parseScorecards(stray), /could not be read/)
  })

  it('rejects repeated templates and unknown schemas', () => {
    const copy = structuredClone(raw)
    copy.scorecards.push(copy.scorecards[0])
    assert.throws(() => parseScorecards(copy), /could not be read/)
    assert.throws(
      () => parseScorecards({ ...raw, schema_version: 2 }),
      /could not be read/,
    )
  })

  it('rounds cost per answer for customers', () => {
    assert.equal(formatCostPerAnswer(0.0031), 'Under 1¢')
    assert.equal(formatCostPerAnswer(0.0262), 'About 3¢')
    assert.equal(formatCostPerAnswer(1.234), 'About $1.23')
  })

  it('formats the test date without shifting time zones', () => {
    assert.equal(formatDate('2026-09-27'), 'September 27, 2026')
  })
})
