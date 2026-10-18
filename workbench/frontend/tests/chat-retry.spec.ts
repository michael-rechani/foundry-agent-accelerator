import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { openWorkspace, send } from './helpers/chat-lab'

test('Try again asks the last question again and keeps the earlier answer', async ({
  page,
}) => {
  const state = await openWorkspace(page, {
    answers: ['First answer', 'Second answer', 'Retried answer'],
  })
  await send(page, 'First question')
  await send(page, 'Second question')
  const turns = page.locator('.turn')

  // Only the latest answer can be tried again.
  await expect(page.getByRole('button', { name: 'Try again' })).toHaveCount(1)
  await expect(
    turns.nth(1).getByRole('button', { name: 'Try again' }),
  ).toBeVisible()
  await expect(page.locator('.earlier-answers')).toHaveCount(0)

  await turns.nth(1).getByRole('button', { name: 'Try again' }).click()
  await expect(turns.nth(1).locator('.message-markdown').first()).toHaveText(
    'Retried answer',
  )
  await expect(turns).toHaveCount(2)

  // The retry repeats the question with only the turns before it as history.
  expect(state.requests).toHaveLength(3)
  expect(state.requests[2]).toMatchObject({
    input: 'Second question',
    history: [
      { role: 'user', content: 'First question' },
      { role: 'assistant', content: 'First answer' },
    ],
  })
  expect(state.requests[2].thread).toBe(state.requests[1].thread)

  const earlier = turns.nth(1).locator('.earlier-answers')
  await expect(earlier.locator('summary')).toContainText('Earlier answer')
  await earlier.locator('summary').click()
  await expect(
    earlier.getByRole('region', { name: 'Earlier answer 1' }),
  ).toContainText('Second answer')
  await expect(turns.nth(0).locator('.earlier-answers')).toHaveCount(0)

  // A further follow-up carries the retried answer, not the earlier one.
  await send(page, 'Third question')
  expect(state.requests[3].history.map((item) => item.content)).toEqual([
    'First question',
    'First answer',
    'Second question',
    'Retried answer',
  ])
  await expect(page.getByRole('button', { name: 'Try again' })).toHaveCount(1)
  await expect(
    turns.nth(2).getByRole('button', { name: 'Try again' }),
  ).toBeVisible()
})

test('trying again twice keeps every earlier answer, oldest first, and the file export', async ({
  page,
}) => {
  await openWorkspace(page, { answers: ['One', 'Two', 'Three'] })
  await send(page, 'Question')
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.locator('.message-markdown').first()).toHaveText('Two')
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.locator('.message-markdown').first()).toHaveText('Three')

  const earlier = page.locator('.earlier-answers')
  await expect(earlier.locator('summary')).toContainText('2 earlier answers')
  await earlier.locator('summary').click()
  await expect(earlier.locator('.earlier-answer')).toHaveCount(2)
  await expect(earlier.locator('.earlier-answer').nth(0)).toContainText('One')
  await expect(earlier.locator('.earlier-answer').nth(1)).toContainText('Two')

  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export conversation' }).click()
  const payload = JSON.parse(
    await readFile((await (await download).path())!, 'utf8'),
  )
  expect(payload.turns).toHaveLength(1)
  expect(payload.turns[0].result.text).toBe('Three')
  expect(
    payload.turns[0].earlier.map((item: { text: string }) => item.text),
  ).toEqual(['One', 'Two'])
})

test('a new answer starts unrated, and earlier answers stay out of shared history', async ({
  page,
}) => {
  const state = await openWorkspace(page, { answers: ['One', 'Two'] })
  await send(page, 'Question')
  await page.getByRole('button', { name: 'Helpful', exact: true }).click()
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.locator('.message-markdown').first()).toHaveText('Two')
  await expect(
    page.getByRole('button', { name: 'Helpful', exact: true }),
  ).toHaveAttribute('aria-pressed', 'false')

  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect.poll(() => state.saves.length).toBe(1)
  expect(state.saves[0].turns).toHaveLength(1)
  expect(JSON.stringify(state.saves[0])).not.toContain('One')
  expect(JSON.stringify(state.saves[0])).not.toContain('earlier')
})

test('a failed retry keeps the current answer and leaves the draft alone', async ({
  page,
}) => {
  await openWorkspace(page, { busyOn: 2, answers: ['Kept answer'] })
  await send(page, 'Question')
  await page.getByRole('textbox', { name: 'Message' }).fill('Half-typed note')
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.locator('.message-markdown').first()).toHaveText(
    'Kept answer',
  )
  await expect(page.locator('.earlier-answers')).toHaveCount(0)
  await expect(page.getByRole('textbox', { name: 'Message' })).toHaveValue(
    'Half-typed note',
  )
  await expect(page.locator('.turn')).toHaveCount(1)
})

test('Try again is disabled while a retry is pending', async ({ page }) => {
  const state = await openWorkspace(page, { holdReview: true })
  await page.getByRole('textbox', { name: 'Message' }).fill('Question')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => state.requests.length).toBe(1)
  await expect(page.getByRole('button', { name: 'Try again' })).toHaveCount(0)
  state.release()
  await expect(page.getByRole('button', { name: 'Try again' })).toBeEnabled()
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect.poll(() => state.requests.length).toBe(2)
  await expect(page.getByRole('button', { name: 'Try again' })).toBeDisabled()
  state.release()
  await expect(page.getByRole('button', { name: 'Try again' })).toBeEnabled()
})
