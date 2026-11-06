import { type Page, expect, test } from '@playwright/test'
import { openWorkspace } from './helpers/chat-lab'

// Stands in for the browser's speech recognition so no microphone is needed.
async function fakeSpeech(page: Page, supported = true) {
  await page.addInitScript((supported) => {
    const recognizers: FakeRecognition[] = []
    class FakeRecognition {
      aborted = false
      stopped = false
      onresult: ((event: unknown) => void) | null = null
      onerror: ((event: { error: string }) => void) | null = null
      onend: (() => void) | null = null
      constructor() {
        recognizers.push(this)
      }
      start() {}
      stop() {
        this.stopped = true
        queueMicrotask(() => this.onend?.())
      }
      abort() {
        this.aborted = true
      }
    }
    const scope = window as unknown as Record<string, unknown>
    scope.__recognizers = recognizers
    delete scope.SpeechRecognition
    delete scope.webkitSpeechRecognition
    if (supported) scope.SpeechRecognition = FakeRecognition
  }, supported)
}

const heard = (page: Page, parts: [string, boolean][]) =>
  page.evaluate((parts) => {
    const list = (window as unknown as { __recognizers: any[] }).__recognizers
    list[list.length - 1].onresult?.({
      results: parts.map(([transcript, isFinal]) =>
        Object.assign([{ transcript }], { isFinal }),
      ),
    })
  }, parts)

const fail = (page: Page, error: string) =>
  page.evaluate((error) => {
    const list = (window as unknown as { __recognizers: any[] }).__recognizers
    const active = list[list.length - 1]
    active.onerror?.({ error })
    active.onend?.()
  }, error)

const state = (page: Page) =>
  page.evaluate(() => {
    const list = (window as unknown as { __recognizers: any[] }).__recognizers
    return {
      count: list.length,
      aborted: list[list.length - 1]?.aborted,
      stopped: list[list.length - 1]?.stopped,
    }
  })

const mic = (page: Page) =>
  page.getByRole('button', { name: 'Dictate message' })
const voiceStatus = (page: Page) => page.locator('.composer-voice-status')
const editor = (page: Page) =>
  page.getByRole('textbox', { name: 'Message', exact: true })

test('the microphone is hidden when the browser has no speech recognition', async ({
  page,
}) => {
  await fakeSpeech(page, false)
  await openWorkspace(page)
  await expect(editor(page)).toBeVisible()
  await expect(mic(page)).toHaveCount(0)
})

test('dictation fills an editable draft and sends nothing until Send', async ({
  page,
}) => {
  await fakeSpeech(page)
  const lab = await openWorkspace(page)
  await editor(page).fill('Build an agent')
  await mic(page).click()
  await expect(mic(page)).toHaveAttribute('aria-pressed', 'true')
  await expect(voiceStatus(page)).toContainText(
    /speech service.*may send it to its provider/,
  )

  await heard(page, [['that reviews', true]])
  await heard(page, [
    ['that reviews', true],
    [' grant applications', false],
  ])
  await expect(editor(page)).toHaveValue(
    'Build an agent that reviews grant applications',
  )
  expect(lab.requests).toEqual([])

  await mic(page).click()
  await expect(mic(page)).toHaveAttribute('aria-pressed', 'false')
  await expect(voiceStatus(page)).toHaveText('')
  expect((await state(page)).stopped).toBe(true)

  await page.getByRole('button', { name: 'Send message' }).click()
  await expect
    .poll(() => lab.requests[0]?.input)
    .toBe('Build an agent that reviews grant applications')
})

test('the privacy details disclose where dictated audio goes', async ({
  page,
}) => {
  await fakeSpeech(page)
  await openWorkspace(page)
  await page.locator('.composer-privacy').getByText('Privacy & sharing').click()
  await expect(page.locator('.dictation-note')).toHaveText(
    "Dictation uses your browser's speech service, which may send audio to its provider. The Lab receives only the text you send.",
  )
})

test('typing while listening ends dictation and keeps what was typed', async ({
  page,
}) => {
  await fakeSpeech(page)
  await openWorkspace(page)
  await mic(page).click()
  await heard(page, [['create an agent', false]])
  await expect(editor(page)).toHaveValue('create an agent')

  await editor(page).pressSequentially('!')
  await expect(mic(page)).toHaveAttribute('aria-pressed', 'false')
  expect((await state(page)).aborted).toBe(true)
  await expect(editor(page)).toHaveValue('create an agent!')
})

test('a blocked microphone explains the problem and how to recover', async ({
  page,
}) => {
  await fakeSpeech(page)
  await openWorkspace(page)
  await mic(page).click()
  await fail(page, 'not-allowed')
  await expect(mic(page)).toHaveAttribute('aria-pressed', 'false')
  await expect(voiceStatus(page)).toContainText(
    "Microphone access is blocked. Allow it in your browser's site settings",
  )

  await mic(page).click()
  await expect(voiceStatus(page)).toContainText('Listening')
  expect((await state(page)).count).toBe(2)
})
