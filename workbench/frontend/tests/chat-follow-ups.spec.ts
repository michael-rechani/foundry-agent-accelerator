import { expect, test, type Page } from '@playwright/test'
import { openAgent, openLibrary } from './helpers/library-lab'
import { support } from './helpers/catalog'

async function openBenefitsAnswer(page: Page) {
  const state = await openLibrary(page, { libraryPreview: true })
  await openAgent(page, 'Benefits renewal helper')
  await page.getByRole('tab', { name: 'Try it' }).click()
  await page
    .getByRole('tabpanel')
    .getByRole('button', { name: 'Try it in Chat' })
    .click()
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => state.chat.length).toBe(1)
  await expect(page.getByRole('group', { name: 'Next steps' })).toBeVisible()
  return state
}

test('the Benefits renewal helper offers next steps that send in one click', async ({
  page,
}) => {
  const state = await openBenefitsAnswer(page)

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

for (const outcome of ['failed', 'stopped'] as const) {
  test(`a ${outcome} follow-up keeps the draft and existing answer without retrying`, async ({
    page,
  }) => {
    await openBenefitsAnswer(page)
    let requests = 0
    await page.route('**/api/reviews', async (route) => {
      requests++
      if (outcome === 'failed')
        await route.fulfill({ status: 503, json: { error: 'agents_busy' } })
    })
    const box = page.getByRole('textbox', { name: 'Message', exact: true })
    const steps = page.getByRole('group', { name: 'Next steps' })
    await box.fill('A half-written thought')
    await steps.getByRole('button', { name: 'Questions for me' }).click()
    await expect.poll(() => requests).toBe(1)
    if (outcome === 'stopped') {
      for (const button of await steps.getByRole('button').all())
        await expect(button).toBeDisabled()
      await box.fill('Edited while waiting')
      await page.getByRole('button', { name: 'Stop waiting' }).click()
    }
    await expect(page.getByRole('alert')).toBeVisible()
    await expect(box).toHaveValue(
      outcome === 'stopped' ? 'Edited while waiting' : 'A half-written thought',
    )
    await expect(page.locator('.turn')).toHaveCount(1)
    await expect(page.locator('.assistant-message')).toContainText(
      'ILLUSTRATIVE ANSWER',
    )
    await expect(
      steps.getByRole('button', { name: 'Questions for me' }),
    ).toBeEnabled()
    expect(requests).toBe(1)
  })
}

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
