import { expect, test } from '@playwright/test'
import { demoScenarios } from '../src/demo-scenarios'
import { templates } from './helpers/catalog'
import { openAgent, openLibrary, readyRecord } from './helpers/library-lab'
import { expectFitsViewport } from './helpers/layout'
import { screenshot } from './fixtures'

const scenario = demoScenarios.find((item) => item.id === 'medical-bill')!
const medical = templates.find((item) => item.id === scenario.templateId)!
const answer =
  'ILLUSTRATIVE TEST RESPONSE: I could not confirm the balance. Please request a revised insurer statement.'

test('the library explains the problem, agent job and expected result before anything runs', async ({
  page,
}, testInfo) => {
  const state = await openLibrary(page, { libraryPreview: true })
  await openAgent(page, medical.label)
  const story = page.getByRole('region', { name: 'Demo story' })
  await expect(story).toContainText('Problem statement')
  await expect(story).toContainText(scenario.problem)
  await expect(story).toContainText('What the agent does')
  await expect(story).toContainText(scenario.agentDoes)
  await expect(story).toContainText('Expected sample result')
  await expect(story).toContainText('not an answer the agent has returned')
  await expect(
    page.getByRole('heading', { name: 'What the agent returned', exact: true }),
  ).toHaveCount(0)
  expect(state.chat).toHaveLength(0)
  expect(state.creations).toBe(0)
  await screenshot(page, testInfo, 'medical-demo-overview.png')

  await page.getByRole('tab', { name: 'Try it', exact: true }).click()
  await expect(story).toContainText(scenario.expectedReturn)
  await page
    .getByRole('tabpanel')
    .getByRole('button', { name: 'Try it in Chat', exact: true })
    .click()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue(medical.sample_input)
  await expect(story).toContainText(scenario.problem)
  expect(state.chat).toHaveLength(0)
  await expectFitsViewport(page)
})

test('presenter view keeps the problem and job beside the actual response without inventing a result', async ({
  page,
}, testInfo) => {
  const state = await openLibrary(page, {
    libraryPreview: true,
    chatAnswer: answer,
  })
  await openAgent(page, medical.label)
  await page
    .getByRole('button', { name: 'Try it in Chat', exact: true })
    .click()
  await page.getByRole('button', { name: 'Presenter view' }).click()
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
  const response = page.locator('.assistant-message')
  await expect(response).toContainText('Problem statement')
  await expect(response).toContainText(scenario.problem)
  await expect(response).toContainText('What the agent does')
  await expect(
    response.getByRole('heading', {
      name: 'What the agent returned',
      exact: true,
    }),
  ).toBeVisible()
  await expect(response.locator('.message-markdown')).toHaveText(answer)
  const body = await response.locator('.message-markdown').boundingBox()
  const viewport = await page.locator('.conversation-scroll').boundingBox()
  expect(body).not.toBeNull()
  expect(viewport).not.toBeNull()
  expect(body!.y + body!.height).toBeLessThanOrEqual(
    viewport!.y + viewport!.height,
  )
  await expect(response).not.toContainText(scenario.expectedReturn)
  await expect(response).not.toContainText('Expected sample result')
  expect(state.chat).toEqual([
    {
      agent_id: `library-${medical.id}`,
      input: medical.sample_input,
      history: [],
      thread: expect.any(String),
    },
  ])
  expect(state.creations).toBe(0)
  await expectFitsViewport(page)
  await screenshot(page, testInfo, 'medical-demo-returned.png')
})

test('a created agent receives the same demo story, without changing its returned answer', async ({
  page,
}) => {
  const record = readyRecord(medical)
  const state = await openLibrary(page, { record, chatAnswer: answer })
  await openAgent(page, medical.label)
  await page
    .getByRole('button', { name: 'Try it in Chat', exact: true })
    .click()
  await expect(page.getByRole('region', { name: 'Demo story' })).toContainText(
    scenario.problem,
  )
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
  await expect(page.locator('.assistant-message .message-markdown')).toHaveText(
    answer,
  )
  await expect(page.locator('.assistant-message')).toContainText(
    'What the agent returned',
  )
  expect(state.chat[0].agent_id).toBe(record.id)
})

test('editing the sample does not attach the original story to a different request', async ({
  page,
}) => {
  const state = await openLibrary(page, {
    libraryPreview: true,
    chatAnswer: answer,
  })
  await openAgent(page, medical.label)
  await page
    .getByRole('button', { name: 'Try it in Chat', exact: true })
    .click()
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Explain what an insurer statement is. Do not review a bill.')
  await expect(page.getByRole('region', { name: 'Demo story' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
  await expect(page.locator('.assistant-message .message-markdown')).toHaveText(
    answer,
  )
  await expect(page.locator('.assistant-message .demo-brief')).toHaveCount(0)
  await expect(
    page.getByRole('heading', { name: 'What the agent returned', exact: true }),
  ).toHaveCount(0)
  expect(state.chat).toHaveLength(1)
})

test('choosing the canonical starter in a fresh chat also restores the demo story', async ({
  page,
}) => {
  const state = await openLibrary(page, {
    record: readyRecord(medical),
    chatAnswer: answer,
  })
  await openAgent(page, medical.label)
  await page
    .getByRole('button', { name: 'Try it in Chat', exact: true })
    .click()
  await page.getByRole('button', { name: 'New chat', exact: true }).click()
  await page
    .getByRole('button', { name: 'Try the sample', exact: true })
    .click()
  await expect(page.getByRole('region', { name: 'Demo story' })).toContainText(
    scenario.problem,
  )
  expect(state.chat).toHaveLength(0)
})

test('loading a follow-up before the sample does not label it as a full bill review', async ({
  page,
}) => {
  await openLibrary(page, { libraryPreview: true, chatAnswer: answer })
  await openAgent(page, medical.label)
  await page
    .getByRole('button', { name: 'Try it in Chat', exact: true })
    .click()
  await page.locator('.demo-run-guide summary').click()
  await page.getByRole('button', { name: /^Load step 2:/ }).click()
  await expect(page.getByRole('region', { name: 'Demo story' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
  await expect(page.locator('.assistant-message .message-markdown')).toHaveText(
    answer,
  )
  await expect(page.locator('.assistant-message .demo-brief')).toHaveCount(0)
})

test('the medical guided demo can load the same sample without creating or sending anything', async ({
  page,
}) => {
  const state = await openLibrary(page, {
    libraryPreview: true,
    hash: '#demos',
  })
  await page
    .getByRole('navigation', { name: 'Demo scenarios' })
    .getByRole('button', { name: /Medical bill review/ })
    .click()
  await expect(page.getByRole('region', { name: 'Demo story' })).toContainText(
    scenario.problem,
  )
  await page
    .getByRole('button', { name: 'Load sample input', exact: true })
    .click()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue(medical.sample_input)
  await expect(page.locator('.demo-run-guide')).toContainText(
    'Medical bill review',
  )
  expect(state.chat).toHaveLength(0)
  expect(state.creations).toBe(0)
})
