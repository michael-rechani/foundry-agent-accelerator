import { type Page, expect, test } from '@playwright/test'
import { openCreation, operatorKey, templates } from './helpers/creation-lab'

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

test('without creation the spec card offers only the download', async ({
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
})
