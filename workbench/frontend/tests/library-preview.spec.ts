import { expect, test } from '@playwright/test'
import { support, templates } from './helpers/catalog'
import { openAgent, openLibrary } from './helpers/library-lab'
import { openChat, workspaceNav } from './helpers/navigation'
import { demoScenarios } from '../src/demo-scenarios'

test('preview explains that nothing is published and catalog failures can be retried', async ({
  page,
}) => {
  const state = await openLibrary(page, { preview: true, catalogFailure: true })
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(
    page.getByRole('heading', { level: 1, name: 'Agent library' }),
  ).toBeVisible()
  state.failCatalog = false
  await page.getByRole('button', { name: 'Retry' }).click()
  await expect(page.locator('.library-card')).toHaveCount(templates.length)
  await openAgent(page, support.label)
  await page.getByRole('tab', { name: 'Try it' }).click()
  await expect(page.getByRole('tabpanel')).toContainText(
    'Local preview: you can prepare and review a setup, but nothing is published.',
  )
  await workspaceNav(page)
    .getByRole('button', { name: /^Request log/ })
    .click()
  await expect(page.locator('.secondary-view')).toContainText(/preview/i)
})

test('a library preview says what the agent will return while the answer is on its way', async ({
  page,
}) => {
  await page.clock.install()
  const state = await openLibrary(page, {
    libraryPreview: true,
    stallChat: true,
  })
  await openAgent(page, support.label)
  await page.getByRole('tab', { name: 'Try it' }).click()
  await page
    .getByRole('tabpanel')
    .getByRole('button', { name: 'Try it in Chat' })
    .click()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue(support.sample_input)
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => state.chat.length).toBe(1)
  expect(state.chat[0].agent_id).toBe(`library-${support.id}`)
  const waiting = page.getByRole('status').filter({ hasText: 'Awaiting' })
  await expect(waiting).toContainText(support.label)
  await expect(waiting).toContainText('Expect:')
  await expect(waiting).toContainText(support.output)
  await expect(waiting).not.toContainText('Still working')
})

test('a library preview offers to create that agent and opens Create with it chosen', async ({
  page,
}) => {
  const state = await openLibrary(page, { libraryPreview: true })
  await openAgent(page, support.label)
  await page.getByRole('button', { name: 'Try it in Chat' }).click()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue(support.sample_input)
  // A preview can't be saved, so Create takes the place of the Save button.
  await expect(
    page.getByRole('button', { name: 'Save to shared history' }),
  ).toHaveCount(0)
  await page
    .getByRole('button', { name: 'Create this agent', exact: true })
    .click()
  await expect(
    page.getByRole('heading', { name: 'Create an agent', exact: true }),
  ).toBeVisible()
  await expect(
    page.locator('.creation-template[aria-pressed="true"]'),
  ).toContainText(support.label)
  await expect(
    page.getByRole('textbox', { name: 'What should the agent help with?' }),
  ).toHaveValue(support.example_request)
  // Moving between the pages sends, prepares and creates nothing.
  expect(state.chat).toHaveLength(0)
  expect(state.drafts).toBe(0)
  expect(state.creations).toBe(0)
})

test('on a wide screen the side column offers to create a previewed agent', async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name === 'mobile',
    'The side column needs a wide window',
  )
  const state = await openLibrary(page, { libraryPreview: true })
  await openAgent(page, support.label)
  await page.getByRole('button', { name: 'Try it in Chat' }).click()
  const aside = page.getByRole('complementary', { name: 'Agent details' })
  await expect(aside.locator('.aside-kind')).toHaveText('Library preview')
  await expect(aside).toContainText(
    'Nothing is created until you confirm on the last step.',
  )
  // A preview can't be saved, so Create takes the place of the Save button.
  await expect(
    aside.getByRole('button', { name: 'Save to shared history' }),
  ).toHaveCount(0)
  await aside
    .getByRole('button', { name: 'Create this agent', exact: true })
    .click()
  await expect(
    page.getByRole('heading', { name: 'Create an agent', exact: true }),
  ).toBeVisible()
  await expect(
    page.locator('.creation-template[aria-pressed="true"]'),
  ).toContainText(support.label)
  expect(state.chat).toHaveLength(0)
  expect(state.drafts).toBe(0)
  expect(state.creations).toBe(0)
})

test('Chat points to Create an agent for something new and cannot create one itself', async ({
  page,
}) => {
  const state = await openLibrary(page)
  await openChat(page)
  const welcome = page.locator('.chat-welcome')
  await expect(welcome).toContainText('Need something else?')
  await expect(
    page.getByRole('button', { name: 'Create this agent', exact: true }),
  ).toHaveCount(0)
  await welcome.getByRole('button', { name: 'Create an agent' }).click()
  await expect(
    page.getByRole('heading', { name: 'Create an agent', exact: true }),
  ).toBeVisible()
  expect(state.chat).toHaveLength(0)
  expect(state.drafts).toBe(0)
  expect(state.creations).toBe(0)
})

test('without agent creation, Chat shows no Create pointer or button', async ({
  page,
}) => {
  await openLibrary(page, { libraryPreview: true, withoutCreation: true })
  await openChat(page)
  await expect(page.locator('.chat-welcome')).toBeVisible()
  await expect(page.locator('.chat-welcome')).not.toContainText(
    'Need something else?',
  )
  await expect(
    page
      .locator('.chat-welcome')
      .getByRole('button', { name: 'Create an agent' }),
  ).toHaveCount(0)
  await workspaceNav(page)
    .getByRole('button', { name: /^All agents/ })
    .click()
  await openAgent(page, support.label)
  await page.getByRole('button', { name: 'Try it in Chat' }).click()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue(support.sample_input)
  await expect(
    page.getByRole('button', { name: 'Create this agent', exact: true }),
  ).toHaveCount(0)
  const save = page.getByRole('button', { name: 'Save to shared history' })
  await expect(save).toBeDisabled()
  await expect(save).toHaveAttribute('title', "Preview chats can't be saved.")
})

test('with library previews on, the invoice guided demo runs as a library preview', async ({
  page,
}) => {
  const invoice = demoScenarios.find((item) => item.id === 'invoice')!
  const state = await openLibrary(page, {
    libraryPreview: true,
    hash: '#demos',
  })
  await page
    .getByRole('navigation', { name: 'Demo scenarios' })
    .getByRole('button', { name: /Supplier invoice review/ })
    .click()
  const note = page.locator('.demo-execution-note')
  await expect(note).toContainText(
    `Uses the ${invoice.templateLabel} library preview.`,
  )
  await expect(note).toContainText('Preview chats are not saved.')
  await expect(
    page.getByRole('button', { name: `Choose ${invoice.templateLabel}` }),
  ).toHaveCount(0)
  await page.getByRole('button', { name: 'Load sample input' }).click()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue(invoice.input)
  await expect(page.locator('.agent-picker')).toContainText(
    invoice.templateLabel,
  )
  expect(state.chat).toEqual([])
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => state.chat.length).toBe(1)
  expect(state.chat[0]).toMatchObject({
    agent_id: 'library-supplier-invoice-reviewer',
    input: invoice.input,
  })
})

test('without library previews, the invoice guided demo still offers to create the agent', async ({
  page,
}) => {
  const invoice = demoScenarios.find((item) => item.id === 'invoice')!
  const state = await openLibrary(page, { hash: '#demos' })
  await page
    .getByRole('navigation', { name: 'Demo scenarios' })
    .getByRole('button', { name: /Supplier invoice review/ })
    .click()
  await expect(
    page.getByRole('button', { name: `Choose ${invoice.templateLabel}` }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Load sample input' }),
  ).toHaveCount(0)
  expect(state.chat).toEqual([])
})
