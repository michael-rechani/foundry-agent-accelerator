import { type Page, expect, test } from '@playwright/test'
import { openCreation, operatorKey, templates } from './helpers/creation-lab'
import { openChat, workspaceNav } from './helpers/navigation'

// Start without stored choices, as a first-time visitor would.
test.use({ storageState: { cookies: [], origins: [] } })

const template = templates[0]
const spec = {
  name: 'Renewal Checklist Helper',
  summary: 'Turns a renewal notice into a short checklist.',
  instructions: 'List what the person must send before the renewal date.',
  inputs: 'A renewal notice',
  outputs: 'A checklist',
  tools_needed: [],
  human_decision: 'A caseworker decides eligibility.',
  closest_template: template.id,
}
const designerAnswer = `Here is the idea.\n\n\`\`\`agent-spec\n${JSON.stringify(spec)}\n\`\`\`\n`

async function askDesigner(page: Page) {
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Help people renew benefits')
  await page.getByRole('button', { name: 'Send message' }).click()
  const card = page.getByRole('region', { name: 'Agent spec' })
  await expect(card).toContainText(spec.name)
  return card
}

test('the spec card can start Create agent on the template it points to', async ({
  page,
}) => {
  const state = await openCreation(page, { hash: '#chat', designerAnswer })
  const card = await askDesigner(page)
  await card
    .getByRole('button', { name: new RegExp(`Start from ${template.label}`) })
    .click()
  await expect(
    page.getByRole('heading', { name: 'Create an agent', level: 1 }),
  ).toBeVisible()
  await expect(
    page.getByRole('textbox', { name: 'What should the agent help with?' }),
  ).toHaveValue(/Turns a renewal notice into a short checklist/)
  expect(state.posts).toEqual([])
})

test('the spec card builds a real agent from the chat only after the key and consent', async ({
  page,
}) => {
  const state = await openCreation(page, { hash: '#chat', designerAnswer })
  const card = await askDesigner(page)
  await card.getByRole('button', { name: 'Create this agent here' }).click()
  const panel = card.getByRole('group', { name: 'Create this agent' })
  await expect(panel).toContainText('real agent in the shared Foundry project')
  await expect(panel).toContainText('keeps costing money')
  const create = panel.getByRole('button', { name: 'Create in Foundry' })
  await expect(create).toBeDisabled()
  await panel.getByRole('checkbox').check()
  await expect(create).toBeEnabled()

  // No key: nothing is sent.
  await create.click()
  await expect(panel.getByRole('alert')).toContainText('operator key')
  expect(state.drafts).toEqual([])
  expect(state.posts).toEqual([])

  await panel.getByLabel('Operator key', { exact: true }).fill(operatorKey)
  await create.click()
  await expect(card.getByRole('status')).toContainText('is ready in Foundry')
  expect(state.drafts).toHaveLength(1)
  expect(state.drafts[0].template_id).toBe(template.id)
  expect(state.posts).toHaveLength(1)
  expect(state.posts[0]).toMatchObject({
    template_id: template.id,
    name: spec.name,
    confirm_cost: true,
  })
  expect(state.keys).toEqual([operatorKey])

  await card.getByRole('button', { name: /Chat with it/ }).click()
  await page
    .getByRole('button', { name: /Switch agent|Start new chat/ })
    .click()
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Check this notice')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.assistant-message').last()).toContainText(
    'ILLUSTRATIVE ANSWER',
  )
  expect(state.chat.at(-1)?.agent_id).toBe(state.record!.id)
})

test('a rejected key does not leave a stuck request', async ({ page }) => {
  const state = await openCreation(page, { hash: '#chat', designerAnswer })
  const card = await askDesigner(page)
  await card.getByRole('button', { name: 'Create this agent here' }).click()
  const panel = card.getByRole('group', { name: 'Create this agent' })
  await panel.getByRole('checkbox').check()
  await panel.getByLabel('Operator key', { exact: true }).fill('x'.repeat(40))
  await panel.getByRole('button', { name: 'Create in Foundry' }).click()
  await expect(panel.getByRole('alert')).toBeVisible()
  expect(state.posts).toHaveLength(1)
  await expect(
    panel.getByRole('button', { name: 'Create in Foundry' }),
  ).toBeVisible()
})

test('private presenter mode builds from chat without a key and keeps cost consent', async ({
  page,
}) => {
  const state = await openCreation(page, {
    hash: '#chat',
    designerAnswer,
    presenter: true,
  })
  const card = await askDesigner(page)
  await card.getByRole('button', { name: 'Create this agent here' }).click()
  const panel = card.getByRole('group', { name: 'Create this agent' })
  await expect(panel.getByLabel('Operator key', { exact: true })).toHaveCount(0)
  await expect(panel).toContainText('Private presenter mode')
  const create = panel.getByRole('button', { name: 'Create in Foundry' })
  await expect(create).toBeDisabled()
  expect(state.posts).toHaveLength(0)
  await panel.getByRole('checkbox').check()
  await create.click()
  await expect(card.getByRole('status')).toContainText('is ready in Foundry')
  expect(state.keys).toEqual([undefined])
  expect(state.posts[0].confirm_cost).toBe(true)
  await page.getByText('Privacy & sharing', { exact: true }).click()
  await expect(page.locator('.composer-privacy')).toContainText(
    'anyone with Lab access can create or delete',
  )
})

test('without creation the spec card offers only downloads', async ({
  page,
}) => {
  await openCreation(page, { hash: '#chat', designerAnswer, disabled: true })
  const card = await askDesigner(page)
  await expect(
    card.getByRole('button', { name: 'Create this agent here' }),
  ).toHaveCount(0)
  await expect(
    card.getByRole('button', { name: 'Download agent spec' }),
  ).toBeVisible()
  await expect(
    card.getByRole('button', { name: 'Download ready-to-deploy agent' }),
  ).toBeVisible()
})

test('an uncertain publication keeps the same request after navigation', async ({
  page,
}) => {
  const state = await openCreation(page, { hash: '#chat', designerAnswer })
  const card = await askDesigner(page)
  await card.getByRole('button', { name: 'Create this agent here' }).click()
  const panel = card.getByRole('group', { name: 'Create this agent' })
  await panel.getByRole('checkbox').check()
  await panel.getByLabel('Operator key', { exact: true }).fill(operatorKey)
  state.loseResponse = true
  await panel.getByRole('button', { name: 'Create in Foundry' }).click()
  await expect(panel.getByRole('alert')).toBeVisible()
  const request = state.posts[0]
  await expect(panel).toContainText(request.idempotency_key)

  await workspaceNav(page).getByRole('button', { name: 'All agents' }).click()
  await openChat(page)
  await expect(panel).toContainText(request.idempotency_key)
  await panel
    .getByRole('button', { name: 'Retry same creation request' })
    .click()
  await expect.poll(() => state.posts.length).toBe(2)
  expect(state.posts[1]).toEqual(request)
  await expect(panel).toContainText('is ready in Foundry')

  const storage = await page.evaluate(() => ({
    local: JSON.stringify(localStorage),
    session: JSON.stringify(sessionStorage),
  }))
  expect(JSON.stringify(storage)).not.toContain(operatorKey)
  expect(JSON.stringify(storage)).not.toContain(request.idempotency_key)
})

test('publication state survives a follow-up chat message', async ({
  page,
}) => {
  const state = await openCreation(page, { hash: '#chat', designerAnswer })
  const card = await askDesigner(page)
  await card.getByRole('button', { name: 'Create this agent here' }).click()
  const panel = card.getByRole('group', { name: 'Create this agent' })
  await panel.getByRole('checkbox').check()
  await panel.getByLabel('Operator key', { exact: true }).fill(operatorKey)
  state.hold = true
  await panel.getByRole('button', { name: 'Create in Foundry' }).click()
  await expect(panel).toContainText('Publishing to Foundry')
  const firstPanel = page
    .getByRole('group', { name: 'Create this agent' })
    .first()
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Explain the next step')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => state.chat.length).toBe(2)
  await expect(firstPanel).toContainText('Publishing to Foundry')
  expect(state.posts).toHaveLength(1)
  state.hold = false
  await expect(firstPanel).toContainText('is ready in Foundry')
})
