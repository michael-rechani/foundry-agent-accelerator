import { expect, test } from '@playwright/test'
import { openDetails, openWorkspace, send } from './helpers/chat-lab'
import { support } from './helpers/catalog'
import { openAgent, openLibrary } from './helpers/library-lab'

test.use({ storageState: { cookies: [], origins: [] } })

const usage = {
  input_tokens: 100,
  output_tokens: 20,
  total_tokens: 120,
  cached_tokens: 0,
  reasoning_tokens: null,
}
const observed = {
  deployment: 'model-router',
  calls: [
    { reported_model: 'gpt-4.1', model_status: 'reported', usage },
    {
      reported_model: 'gpt-4.1-mini',
      model_status: 'reported',
      usage: {
        ...usage,
        input_tokens: 150,
        output_tokens: 40,
        total_tokens: 190,
      },
    },
    { reported_model: null, model_status: 'not_reported', usage: null },
    { reported_model: null, model_status: 'invalid', usage: null },
  ],
}

test('direct preview reports each model call without inferring routing', async ({
  page,
}, testInfo) => {
  const state = await openLibrary(page, {
    libraryPreview: true,
    chatObservation: observed,
    chatUsage: null,
  })
  await page.getByRole('switch', { name: /Under the hood/ }).check()
  await openAgent(page, support.label)
  await page.getByRole('button', { name: 'Try it in Chat' }).click()
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.assistant-message')).toHaveCount(1)
  expect(state.chat[0].agent_id).toBe(`library-${support.id}`)
  const details = await openDetails(page)
  await details.locator('.receipt-details > summary').click()
  const model = details.getByRole('region', { name: 'Direct model calls' })
  await expect(details.locator('.usage-detail')).toContainText(
    'Complete token totals were not reported for this answer.',
  )
  await expect(details.locator('.usage-detail')).toContainText(
    'a count missing from any call is not totaled',
  )
  await expect(model).toContainText('Requested deployment: model-router')
  const calls = model
    .getByRole('list', { name: 'Reported model calls' })
    .getByRole('listitem')
  await expect(calls).toHaveCount(4)
  await expect(calls.nth(0)).toContainText('Reported model: gpt-4.1')
  await expect(calls.nth(0)).toContainText('Tokens: 100 input')
  await expect(calls.nth(0)).toContainText('0 cached input')
  await expect(calls.nth(0)).toContainText('reasoning not reported')
  await expect(calls.nth(1)).toContainText('Reported model: gpt-4.1-mini')
  await expect(calls.nth(2)).toContainText('Model name not reported.')
  await expect(calls.nth(2)).toContainText('Token usage not reported.')
  await expect(calls.nth(3)).toContainText(
    'The reported model name was invalid.',
  )
  await expect(model).toContainText(
    'does not by itself prove which model served',
  )
  await expect(model).toContainText(
    'Model names and token counts were reported by the service.',
  )
  await expect(page.locator('.assistant-heading')).toContainText(
    'Token total not reported',
  )
  await expect(
    page.getByRole('complementary', { name: 'Agent details' }),
  ).toContainText('Complete totals not reported')
  await model.scrollIntoViewIfNeeded()
  await page.screenshot({
    path: testInfo.outputPath('model-observation-desktop.png'),
    animations: 'disabled',
  })
  await page.getByRole('switch', { name: /Under the hood/ }).uncheck()
  await expect(model).toBeHidden()
})

test('designer details survive saving and are labeled unverified when reopened', async ({
  page,
}) => {
  const singleCall = { ...observed, calls: [observed.calls[0]] }
  const state = await openWorkspace(page, {
    config: {
      library_preview: {
        enabled: true,
        reason: null,
        agent: 'lab-library-preview',
      },
    },
    startup: true,
    receipts: [],
    modelObservation: singleCall,
  })
  await send(page, 'Help me design an agent')
  expect(state.requests[0].agent_id).toBe('library-agent-designer')
  const modelDetails = page.locator('.receipt-details')
  await expect(modelDetails).toBeHidden()
  await page.getByRole('switch', { name: /Under the hood/ }).check()
  await modelDetails.locator('summary').click()
  await expect(modelDetails).toContainText('Requested deployment: model-router')
  await expect(modelDetails).not.toContainText('not reverified')
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect.poll(() => state.saves.length).toBe(1)
  expect(state.saves[0].turns[0].result.model_observation).toEqual(singleCall)
  await page.reload()
  await page.getByRole('button', { name: /^Shared history/ }).click()
  await page.locator('.saved-open').click()
  const savedDetails = page.locator('.receipt-details')
  await savedDetails.locator('summary').click()
  await expect(savedDetails).toContainText(
    'Saved values are not reverified after reopening.',
  )
  await expect(savedDetails).toContainText('Reported model: gpt-4.1')
  expect(state.requests).toHaveLength(1)
})

test('hosted answers cannot claim direct model attribution', async ({
  page,
}) => {
  const state = await openWorkspace(page, {
    startup: true,
    modelObservation: observed,
  })
  await page.getByRole('switch', { name: /Under the hood/ }).check()
  await send(page)
  const details = await openDetails(page)
  await details.locator('.receipt-details > summary').click()
  await expect(details).toContainText('Model details could not be read.')
  await expect(details).not.toContainText('gpt-4.1')
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect.poll(() => state.saves.length).toBe(1)
  expect(state.saves[0].turns[0].result.model_observation).toBeNull()
})
