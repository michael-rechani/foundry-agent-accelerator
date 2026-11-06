import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  appendTranscript,
  recognizerConstructor,
  transcriptOf,
  voiceErrorMessage,
} from '../src/voice-input.ts'

const result = (transcript: string, isFinal = true) => ({
  isFinal,
  length: 1,
  0: { transcript },
})

describe('transcriptOf', () => {
  it('joins every result so far into one transcript', () => {
    assert.equal(
      transcriptOf([result(' create an agent '), result('for grants', false)]),
      'create an agent for grants',
    )
  })

  it('ignores empty results', () => {
    assert.equal(transcriptOf([result('  '), result('hello')]), 'hello')
    assert.equal(transcriptOf([]), '')
  })
})

describe('appendTranscript', () => {
  it('starts an empty draft with the transcript', () => {
    assert.equal(appendTranscript('', 'review grants'), 'review grants')
    assert.equal(appendTranscript('  \n', 'review grants'), 'review grants')
  })

  it('adds a space after typed text and keeps existing whitespace', () => {
    assert.equal(
      appendTranscript('Build an agent', 'for intake'),
      'Build an agent for intake',
    )
    assert.equal(
      appendTranscript('Build an agent\n', 'for intake'),
      'Build an agent\nfor intake',
    )
  })

  it('keeps the draft when nothing was heard', () => {
    assert.equal(appendTranscript('Draft', '  '), 'Draft')
  })

  it('collapses spoken whitespace', () => {
    assert.equal(appendTranscript('', 'one   two\nthree'), 'one two three')
  })
})

describe('recognizerConstructor', () => {
  class Standard {}
  class Prefixed {}

  it('prefers the standard name and falls back to the prefixed one', () => {
    assert.equal(
      recognizerConstructor({
        SpeechRecognition: Standard as never,
        webkitSpeechRecognition: Prefixed as never,
      }),
      Standard,
    )
    assert.equal(
      recognizerConstructor({ webkitSpeechRecognition: Prefixed as never }),
      Prefixed,
    )
  })

  it('returns nothing when the browser has no speech recognition', () => {
    assert.equal(recognizerConstructor({}), undefined)
  })
})

describe('voiceErrorMessage', () => {
  it('stays silent when the user stops dictation', () => {
    assert.equal(voiceErrorMessage('aborted'), null)
  })

  it('names the problem and the recovery', () => {
    assert.match(
      voiceErrorMessage('not-allowed')!,
      /blocked.*type your message/,
    )
    assert.match(voiceErrorMessage('service-not-allowed')!, /blocked/)
    assert.match(voiceErrorMessage('no-speech')!, /try again/)
    assert.match(voiceErrorMessage('audio-capture')!, /No microphone/)
    assert.match(voiceErrorMessage('network')!, /couldn't be reached/)
    assert.match(voiceErrorMessage('anything-else')!, /stopped unexpectedly/)
  })
})
