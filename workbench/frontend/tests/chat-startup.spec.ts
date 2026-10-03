import { expect, test } from '@playwright/test'
import { agent, openWorkspace } from './helpers/chat-lab'

test('startup timeout preserves a draft and supports explicit retry', async ({
  page,
}, testInfo) => {
  await page.clock.install()
  const state = await openWorkspace(page, { startup: 'stalled' })
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Keep my synthetic draft')
  await expect(
    page.getByRole('button', { name: 'Send message' }),
  ).toBeDisabled()
  await page.clock.runFor(15001)
  await expect(page.getByRole('alert')).toContainText('configuration timed out')
  await page.screenshot({ path: testInfo.outputPath('startup-recovery.png') })
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Send message' })).toBeEnabled()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue('Keep my synthetic draft')
  expect(state.configRequests).toBe(2)
  expect(state.requests).toHaveLength(0)
})

for (const startup of ['invalid', 'invalid-guidance', 'failed'] as const) {
  test(`${startup} startup configuration fails closed and recovers`, async ({
    page,
  }) => {
    const state = await openWorkspace(page, { startup })
    await expect(page.getByRole('alert')).toContainText(
      'configuration unavailable or invalid',
    )
    await expect(
      page.getByRole('button', { name: 'Send message' }),
    ).toBeDisabled()
    await page.getByRole('button', { name: 'Retry', exact: true }).click()
    await expect(
      page.getByRole('button', { name: 'Check against a checklist' }),
    ).toBeVisible()
    expect(state.configRequests).toBe(2)
  })
}

test('configured title, default agent, prompts and character limits drive the UI', async ({
  page,
}) => {
  const specialist = {
    ...agent,
    id: 'case-review',
    label: 'Casework assistance',
    prompts: [{ label: 'Check a date', text: 'CASE-1' }],
  }
  const state = await openWorkspace(page, {
    config: {
      title: 'Foundry Agent Test Lab',
      agents: [agent, specialist],
      default_agent: specialist.id,
      max_characters: 6,
    },
  })
  await expect(page).toHaveTitle('Foundry Agent Test Lab')
  await page.getByRole('button', { name: 'Check a date' }).click()
  const editor = page.getByRole('textbox', { name: 'Message', exact: true })
  await expect(editor).toHaveValue('CASE-1')
  await expect(page.getByRole('button', { name: 'Send message' })).toBeEnabled()
  await editor.fill('\u{1F600}'.repeat(6))
  await expect(page.getByRole('button', { name: 'Send message' })).toBeEnabled()
  await editor.fill('CASE-12')
  await expect(page.getByRole('alert')).toContainText(
    'Character limit exceeded',
  )
  await expect(
    page.getByRole('button', { name: 'Send message' }),
  ).toBeDisabled()
  expect(state.requests).toHaveLength(0)
})
