import { expect, test } from '@playwright/test'
import { openAgent, openLibrary } from './helpers/library-lab'
import { support } from './helpers/catalog'

test('the Benefits renewal helper offers next steps that send in one click', async ({
  page,
}) => {
  const state = await openLibrary(page, { libraryPreview: true })
  await openAgent(page, 'Benefits renewal helper')
  await page.getByRole('tab', { name: 'Try it' }).click()
  await page
    .getByRole('tabpanel')
    .getByRole('button', { name: 'Try it in Chat' })
    .click()
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => state.chat.length).toBe(1)

  const steps = page.getByRole('group', { name: 'Next steps' })
  await expect(
    steps.getByRole('button', { name: 'See the proof-by-proof checklist' }),
  ).toBeVisible()

  const box = page.getByRole('textbox', { name: 'Message', exact: true })
  await box.fill('A half-written thought')
  await steps
    .getByRole('button', { name: 'Draft the note to the household' })
    .click()
  await expect.poll(() => state.chat.length).toBe(2)
  expect(state.chat[1].agent_id).toBe('library-benefits-renewal-helper')
  expect(state.chat[1].input).toContain('Draft the note to the household')
  await expect(box).toHaveValue('A half-written thought')
  await expect(page.getByRole('group', { name: 'Next steps' })).toHaveCount(1)
})

test('agents without a guided conversation show no next steps', async ({
  page,
}) => {
  const state = await openLibrary(page, { libraryPreview: true })
  await openAgent(page, support.label)
  await page.getByRole('tab', { name: 'Try it' }).click()
  await page
    .getByRole('tabpanel')
    .getByRole('button', { name: 'Try it in Chat' })
    .click()
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => state.chat.length).toBe(1)
  await expect(page.locator('.assistant-message')).toBeVisible()
  await expect(page.getByRole('group', { name: 'Next steps' })).toHaveCount(0)
})
