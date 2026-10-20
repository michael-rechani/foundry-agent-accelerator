import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { openWorkspace, send } from './helpers/chat-lab'

test('a tester can rate an answer, change it, clear it, export it and save it', async ({
  page,
}) => {
  const state = await openWorkspace(page, { answers: ['First', 'Second'] })
  await send(page, 'First question')
  await send(page, 'Second question')
  const first = page.locator('.turn').nth(0)
  const second = page.locator('.turn').nth(1)
  const aside = page.getByRole('complementary', { name: 'Agent details' })

  await first.getByRole('button', { name: 'Helpful', exact: true }).click()
  await expect(
    first.getByRole('button', { name: 'Helpful', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true')
  await expect(aside).toContainText('1 helpful')

  await second.getByRole('button', { name: 'Not helpful' }).click()
  await second
    .getByRole('textbox', { name: 'Reason (optional)' })
    .fill('Wrong total')
  await expect(aside).toContainText('1 helpful, 1 not helpful')

  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export conversation' }).click()
  const payload = JSON.parse(
    await readFile((await (await download).path())!, 'utf8'),
  )
  expect(payload.turns[0].rating).toEqual({ value: 'up' })
  expect(payload.turns[1].rating).toEqual({
    value: 'down',
    reason: 'Wrong total',
  })

  // Changing the thumb keeps the other answer's rating.
  await second.getByRole('button', { name: 'Helpful', exact: true }).click()
  await expect(aside).toContainText('2 helpful')
  await expect(
    second.getByRole('button', { name: 'Not helpful' }),
  ).toHaveAttribute('aria-pressed', 'false')

  // Choosing the same thumb again clears it.
  await first.getByRole('button', { name: 'Helpful', exact: true }).click()
  await expect(aside).toContainText('1 helpful')
  await second.getByRole('button', { name: 'Helpful', exact: true }).click()
  await expect(aside).not.toContainText('Your ratings')
  await expect(
    first.getByRole('textbox', { name: 'Reason (optional)' }),
  ).toHaveCount(0)

  // Ratings are saved with the conversation and come back when it is reopened.
  await first.getByRole('button', { name: 'Not helpful' }).click()
  await first
    .getByRole('textbox', { name: 'Reason (optional)' })
    .fill('Missed the budget')
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect.poll(() => state.saves.length).toBe(1)
  expect(state.saves[0].turns.map((turn) => turn.rating)).toEqual([
    { value: 'down', reason: 'Missed the budget' },
    undefined,
  ])
  await expect(
    page.getByText('Saved / shared', { exact: true }).filter({ visible: true }),
  ).toBeVisible()

  // Changing a rating after saving marks the chat as changed.
  await second.getByRole('button', { name: 'Helpful', exact: true }).click()
  await expect(
    page
      .getByText('Unsaved changes', { exact: true })
      .filter({ visible: true }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect.poll(() => state.saves.length).toBe(2)
  expect(state.saves[1].turns[1].rating).toEqual({ value: 'up' })

  await page.getByRole('button', { name: 'New chat', exact: true }).click()
  await page.getByRole('button', { name: /^Shared history/ }).click()
  await page.locator('.saved-open').click()
  const reopened = page.locator('.turn')
  await expect(
    reopened.nth(0).getByRole('button', { name: 'Not helpful' }),
  ).toHaveAttribute('aria-pressed', 'true')
  await expect(
    reopened.nth(0).getByRole('textbox', { name: 'Reason (optional)' }),
  ).toHaveValue('Missed the budget')
  await expect(
    reopened.nth(1).getByRole('button', { name: 'Helpful', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true')
  await expect(aside).toContainText('1 helpful, 1 not helpful')
})

test('a new chat starts without ratings', async ({ page }) => {
  await openWorkspace(page)
  await send(page)
  await page.getByRole('button', { name: 'Helpful', exact: true }).click()
  await expect(
    page.getByRole('button', { name: 'Helpful', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: 'New chat', exact: true }).click()
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Start new chat' })
    .click()
  await send(page)
  await expect(
    page.getByRole('button', { name: 'Helpful', exact: true }),
  ).toHaveAttribute('aria-pressed', 'false')
})
