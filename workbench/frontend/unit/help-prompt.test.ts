import assert from 'node:assert/strict'
import test from 'node:test'
import { isHelpQuestion } from '../src/help-prompt.ts'

const prompts = [
  { label: 'Review a case', text: 'Summarize these notes.' },
  { label: 'Help me get started', text: 'What can you help me with?' },
]

test('the Help me get started prompt is a help question', () => {
  assert.equal(isHelpQuestion('What can you help me with?', prompts), true)
  assert.equal(isHelpQuestion('  What can you help me with?\n', prompts), true)
})

test('other prompts and typed questions are not help questions', () => {
  assert.equal(isHelpQuestion('Summarize these notes.', prompts), false)
  assert.equal(isHelpQuestion('What can you do?', prompts), false)
  assert.equal(isHelpQuestion('', prompts), false)
  assert.equal(isHelpQuestion('What can you help me with?', undefined), false)
})
