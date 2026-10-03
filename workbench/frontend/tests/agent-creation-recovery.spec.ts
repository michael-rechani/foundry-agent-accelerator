import { expect, test } from '@playwright/test'
import { guidedReview } from './fixtures'
import {
  authorize,
  navigate,
  openCreation,
  openSaved,
  operatorKey,
  prepare,
  recordFor,
} from './helpers/creation-lab'
import { parseCreatedAgent } from '../src/agent-creation-client'

test('uncertain response retains the same UUID and body for explicit retry only', async ({
  page,
}) => {
  await page.clock.install()
  const state = await openCreation(page)
  state.loseResponse = true
  await prepare(page)
  await authorize(page)
  await page
    .getByRole('button', { name: 'Create in Foundry', exact: true })
    .click()
  await expect(
    page.getByRole('button', { name: 'Retry same creation request' }),
  ).toBeVisible()
  await expect(page.getByLabel('Agent name', { exact: true })).toBeDisabled()
  await page.clock.fastForward(35000)
  expect(state.posts).toHaveLength(1)
  await page.getByRole('button', { name: 'Check creation status' }).click()
  await expect(page.getByRole('alert')).toContainText('No saved agent record')
  await page
    .getByRole('button', { name: 'Retry same creation request' })
    .click()
  await expect(page.locator('.creation-status')).toHaveText('Ready to try')
  expect(state.posts).toHaveLength(2)
  expect(state.posts[1]).toEqual(state.posts[0])
})

test('lost response with a saved operation recovers using GET, never another publication', async ({
  page,
}) => {
  const state = await openCreation(page)
  state.loseResponse = true
  state.persistLostResponse = true
  await prepare(page)
  await authorize(page)
  await page
    .getByRole('button', { name: 'Create in Foundry', exact: true })
    .click()
  await expect(
    page.getByRole('button', { name: 'Check creation status' }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Check creation status' }).click()
  await expect(page.locator('.creation-status')).toHaveText('Ready to try')
  expect(state.posts).toHaveLength(1)
})

test('poll failure pauses checks until explicit refresh without posting again', async ({
  page,
}) => {
  await page.clock.install()
  const state = await openCreation(page)
  state.pollFailures = 1
  await prepare(page)
  await authorize(page)
  await page
    .getByRole('button', { name: 'Create in Foundry', exact: true })
    .click()
  await expect(page.getByRole('status')).toContainText(
    'automatic checks paused',
  )
  const reads = state.polls
  await page.clock.fastForward(45000)
  expect(state.polls).toBe(reads)
  expect(state.posts).toHaveLength(1)
  await page.getByRole('button', { name: 'Refresh status' }).click()
  await expect(page.locator('.creation-status')).toHaveText('Ready to try')
  expect(state.posts).toHaveLength(1)
})

test('ready agents persist across reload and new-chat confirmation preserves unsaved messages', async ({
  page,
}) => {
  const state = await openCreation(page, { saved: recordFor() })
  await navigate(page, 'Chat')
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Keep this fictional unsent message')
  await openSaved(page)
  page.once('dialog', (dialog) => dialog.dismiss())
  await page.getByRole('button', { name: 'Try in Chat', exact: true }).click()
  await expect(
    page.getByRole('region', { name: 'Created agent details' }),
  ).toBeVisible()
  await navigate(page, 'Chat')
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue('Keep this fictional unsent message')
  await navigate(page, 'Created agents')
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Try in Chat', exact: true }).click()
  await expect(page.locator('.agent-picker')).toContainText(
    'Policy notice helper',
  )
  await page.reload()
  await openSaved(page)
  await expect(page.locator('.creation-status')).toHaveText('Ready to try')
  expect(state.posts).toHaveLength(0)
})

test('leaving creation removes the password without losing the prepared task', async ({
  page,
}) => {
  await openCreation(page)
  await prepare(page)
  await page.getByLabel('Operator key', { exact: true }).fill(operatorKey)
  await navigate(page, 'Chat')
  await expect(page.locator('input[type="password"]')).toHaveCount(0)
  await navigate(page, 'Create agent')
  await expect(page.getByLabel('Agent name', { exact: true })).toHaveValue(
    'Document explainer',
  )
  await expect(page.getByLabel('Operator key', { exact: true })).toHaveValue('')
  expect(
    await page.evaluate(() =>
      JSON.stringify({ ...localStorage, ...sessionStorage }),
    ),
  ).not.toContain(operatorKey)
})

test('deletion stays available with creation disabled and requires confirmation and current ETag', async ({
  page,
}) => {
  const state = await openCreation(page, { disabled: true, saved: recordFor() })
  await openSaved(page)
  await page.getByLabel('Operator key', { exact: true }).fill(operatorKey)
  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('for everyone')
    expect(dialog.message()).toContain('Export needed chats first')
    await dialog.dismiss()
  })
  await page.getByRole('button', { name: 'Delete created agent' }).click()
  expect(state.deletes).toBe(0)
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Delete created agent' }).click()
  await expect(page.locator('.creation-status')).toHaveText('Deleted')
  await expect(page.locator('.creation-detail')).toContainText(
    'Deletion was confirmed',
  )
  await expect(
    page.getByRole('button', { name: 'Try in Chat', exact: true }),
  ).toHaveCount(0)
  expect(state.record!.instructions).toBe('')
  expect(state.deletes).toBe(1)
  expect(state.posts).toHaveLength(0)
  await page.getByRole('button', { name: 'Back to Made in this Lab' }).click()
  await expect(page.locator('.created-agent-list')).toHaveCount(0)
})

test('interrupted setup resumes an existing operation, but interrupted deletion cannot resume setup', async ({
  page,
}) => {
  const interrupted = {
    ...recordFor('interrupted'),
    error: 'publication_unconfirmed',
  }
  const state = await openCreation(page, { saved: interrupted })
  await openSaved(page)
  await page.getByLabel('Operator key', { exact: true }).fill(operatorKey)
  await page.getByRole('button', { name: 'Resume setup' }).click()
  await expect(page.locator('.creation-status')).toHaveText('Ready to try')
  expect(state.resumes).toBe(1)
  expect(state.posts).toHaveLength(0)
  state.deletionFailure = true
  await page.getByLabel('Operator key', { exact: true }).fill(operatorKey)
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Delete created agent' }).click()
  await expect(page.locator('.creation-status')).toHaveText('Check outcome')
  await expect(page.locator('.creation-detail')).toContainText(
    'Deletion is not confirmed',
  )
  await expect(page.getByRole('button', { name: 'Resume setup' })).toHaveCount(
    0,
  )
  await page.getByLabel('Operator key', { exact: true }).fill(operatorKey)
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Delete created agent' }).click()
  await expect(page.locator('.creation-status')).toHaveText('Deleted')
  expect(state.deletes).toBe(2)
})

test('template and collection errors stay visible and can be refreshed', async ({
  page,
}) => {
  const state = await openCreation(page, {
    templateFailure: true,
    listFailure: true,
  })
  await expect(
    page.getByRole('button', { name: 'Retry templates' }),
  ).toBeVisible()
  state.templateFailure = false
  await page.getByRole('button', { name: 'Retry templates' }).click()
  await expect(page.locator('.creation-template')).toHaveCount(9)
  await navigate(page, 'Created agents')
  await expect(page.getByRole('alert')).toContainText('storage is unavailable')
  state.listFailure = false
  await page.getByRole('button', { name: 'Refresh agents' }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  expect(state.posts).toHaveLength(0)
})

test('malformed prepared setup cannot become a publishable draft', async ({
  page,
}) => {
  const state = await openCreation(page)
  state.invalidDraft = true
  await page.locator('.creation-template').first().click()
  await page.getByRole('button', { name: 'Prepare setup', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText(
    'prepared setup response is invalid',
  )
  await expect(
    page.getByRole('button', { name: 'Create in Foundry', exact: true }),
  ).toHaveCount(0)
  expect(state.posts).toHaveLength(0)
})

test('saved-review links still open document reviews instead of the new default entry', async ({
  page,
}) => {
  const state = await openCreation(page, {
    hash: '#review-12345678-1234-1234-1234-123456789abc',
  })
  await expect(
    page.getByRole('heading', { name: 'Document reviews', exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'Create an agent', exact: true }),
  ).toBeHidden()
  expect(state.posts).toHaveLength(0)
  expect(state.chat).toHaveLength(0)
})

test('created-record validation rejects mismatched identities and accepts cleared deletion tombstones', () => {
  const record = recordFor()
  expect(parseCreatedAgent(record).id).toBe(record.id)
  expect(parseCreatedAgent(recordFor('deleted')).instructions).toBe('')
  expect(() =>
    parseCreatedAgent({
      ...record,
      agent: { ...record.agent!, id: guidedReview.id },
    }),
  ).toThrow()
  expect(() =>
    parseCreatedAgent({
      ...record,
      agent: { ...record.agent!, agent: guidedReview.agent },
    }),
  ).toThrow()
  expect(() => parseCreatedAgent({ ...record, status: 'creating' })).toThrow()
  expect(() =>
    parseCreatedAgent({ ...record, model_profile: { id: 'reasoning' } }),
  ).toThrow()
  expect(
    parseCreatedAgent({ ...record, model_profile: undefined }).model_profile,
  ).toBeUndefined()
  expect(() => parseCreatedAgent({ ...record, instructions: '' })).toThrow()
})
