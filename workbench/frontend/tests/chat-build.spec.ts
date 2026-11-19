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

test('a no-template spec tries and publishes the exact reviewed text, then chats only with its ready agent', async ({
  page,
}) => {
  const promptSpec = { ...spec, closest_template: null, tools_needed: ['CRM'] }
  const state = await openCreation(page, {
    hash: '#chat',
    designerAnswer: designerAnswer.replace(
      JSON.stringify(spec),
      JSON.stringify(promptSpec),
    ),
  })
  const tries: unknown[] = []
  await page.route('**/api/prompt-agent-tries', async (route) => {
    tries.push(route.request().postDataJSON())
    await route.fulfill({ json: { text: 'Mock draft response.' } })
  })
  const card = await askDesigner(page)
  await expect(
    card.getByRole('button', { name: 'Download ready-to-deploy agent' }),
  ).toBeVisible()
  await card.getByRole('button', { name: 'Review prompt-only agent' }).click()
  const panel = card.getByRole('group', { name: 'Create this agent' })
  const instructions = panel.getByLabel('Task instructions')
  await expect(instructions).toHaveValue(spec.instructions)
  const create = panel.getByRole('button', { name: 'Create in Foundry' })
  await instructions.fill('short')
  await expect(create).toBeDisabled()
  const reviewed =
    '\nUse the fictional notice and list only the missing dates.\n'
  await instructions.fill(reviewed)
  await panel
    .getByText('Try these instructions (optional)', { exact: true })
    .click()
  const sample = 'Fictional notice: a date is missing.'
  await panel.getByLabel('Sample message').fill(sample)
  const run = panel.getByRole('button', { name: 'Run one try' })
  await expect(run).toBeDisabled()
  await panel.getByLabel('I confirm this try can incur model charges.').check()
  await run.click()
  await expect(panel.getByText('Mock draft response.')).toBeVisible()
  expect(tries).toEqual([
    { instructions: reviewed, prompt: sample, confirm_cost: true },
  ])
  expect(state.posts).toHaveLength(0)
  await expect(create).toBeDisabled()

  await panel.getByLabel(/I confirm creating a shared Foundry agent/).check()
  await create.click()
  await expect(panel.getByRole('alert')).toContainText('operator key')
  expect(state.posts).toHaveLength(0)
  await panel.getByLabel('Operator key', { exact: true }).fill(operatorKey)
  state.loseResponse = true
  state.persistLostResponse = true
  state.hold = true
  await create.dblclick()
  await expect(panel.getByRole('alert')).toBeVisible()
  await expect(panel.getByRole('button', { name: /Chat with it/ })).toHaveCount(
    0,
  )
  await panel.getByRole('button', { name: 'Check creation status' }).click()
  await expect(panel).toContainText('Publishing to Foundry')
  expect(state.drafts).toEqual([])
  expect(state.posts).toHaveLength(1)
  expect(state.posts[0]).toMatchObject({
    instructions: reviewed,
    confirm_cost: true,
    template_id: 'prompt-only',
  })
  state.hold = false
  await panel.getByRole('button', { name: /Chat with it/ }).click()
  await page
    .getByRole('button', { name: /Switch agent|Start new chat/ })
    .click()
  await page.getByRole('textbox', { name: 'Message', exact: true }).fill(sample)
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => state.chat.at(-1)?.agent_id).toBe(state.record!.id)
})

const noTemplateAnswer = designerAnswer.replace(
  JSON.stringify(spec),
  JSON.stringify({ ...spec, closest_template: null }),
)

async function openPromptReview(page: Page) {
  const card = await askDesigner(page)
  await card.getByRole('button', { name: 'Review prompt-only agent' }).click()
  return card.getByRole('group', { name: 'Create this agent' })
}

for (const persisted of [true, false]) {
  test(`prompt-only reload recovers an ambiguous submission (${persisted ? 'saved' : 'no record yet'})`, async ({
    page,
  }) => {
    const state = await openCreation(page, {
      hash: '#chat',
      designerAnswer: noTemplateAnswer,
    })
    let panel = await openPromptReview(page)
    const original = 'List only the missing dates in the fictional notice.'
    await panel.getByLabel('Task instructions').fill(original)
    await panel.getByLabel('Operator key', { exact: true }).fill(operatorKey)
    await panel.getByLabel(/I confirm creating a shared Foundry agent/).check()
    state.loseResponse = true
    state.persistLostResponse = persisted
    await panel.getByRole('button', { name: 'Create in Foundry' }).click()
    await expect(panel.getByRole('alert')).toBeVisible()
    expect(state.posts).toHaveLength(1)
    const request = state.posts[0]
    const receipt = await page.evaluate(() =>
      localStorage.getItem('foundry-lab.prompt-creation.v1'),
    )
    expect(JSON.parse(receipt!)).toEqual({
      id: request.idempotency_key,
      fingerprint: expect.stringMatching(/^[0-9a-f]{64}$/),
    })
    expect(receipt).not.toContain(original)
    expect(receipt).not.toContain(spec.name)
    const storage = await page.evaluate(() =>
      JSON.stringify([localStorage, sessionStorage]),
    )
    expect(storage).not.toContain(operatorKey)

    await page.reload()
    panel = await openPromptReview(page)
    const retry = panel.getByRole('button', {
      name: 'Retry same creation request',
    })
    await expect(retry).toBeDisabled()
    await expect(panel.getByLabel('Operator key', { exact: true })).toHaveValue(
      '',
    )
    await expect(panel).toContainText(request.idempotency_key)

    if (!persisted) {
      state.record = null
      await panel.getByRole('button', { name: 'Check creation status' }).click()
      await expect(panel.getByRole('alert')).toContainText(
        'No saved agent was found yet',
      )
      await expect(retry).toBeDisabled()
      await panel.getByLabel('Operator key', { exact: true }).fill(operatorKey)
      await panel
        .getByLabel(/I confirm creating a shared Foundry agent/)
        .check()
      await retry.click()
      await expect(panel.getByRole('alert')).toContainText(
        'exact task instructions',
      )
      expect(state.posts).toHaveLength(1)
      await panel.getByLabel('Task instructions').fill(original)
      await panel
        .getByLabel(/I confirm creating a shared Foundry agent/)
        .check()
      await retry.click()
      await expect(panel).toContainText('Publishing to Foundry')
      expect(state.posts).toEqual([request, request])
    } else {
      await panel.getByRole('button', { name: 'Check creation status' }).click()
    }

    await expect(panel).toContainText('is ready in Foundry')
    expect(state.record?.id).toBe('created-' + request.idempotency_key)
    expect(state.posts).toHaveLength(persisted ? 1 : 2)
    await panel
      .getByRole('button', { name: 'Finish tracking this request' })
      .click()
    await expect
      .poll(() =>
        page.evaluate(() =>
          localStorage.getItem('foundry-lab.prompt-creation.v1'),
        ),
      )
      .toBeNull()
  })
}

for (const method of ['getItem', 'setItem'] as const) {
  test(`prompt-only creation sends nothing if browser storage cannot ${method === 'getItem' ? 'read' : 'write'} its receipt`, async ({
    page,
  }) => {
    await page.addInitScript((name) => {
      const original = Storage.prototype[name]
      Object.defineProperty(Storage.prototype, name, {
        value: function (this: Storage, key: string, value: string) {
          if (key === 'foundry-lab.prompt-creation.v1')
            throw new DOMException('Storage blocked', 'SecurityError')
          return Reflect.apply(original, this, [key, value])
        },
      })
    }, method)
    const state = await openCreation(page, {
      hash: '#chat',
      designerAnswer: noTemplateAnswer,
    })
    const panel = await openPromptReview(page)
    const create = panel.getByRole('button', { name: 'Create in Foundry' })
    await panel.getByLabel('Operator key', { exact: true }).fill(operatorKey)
    await panel.getByLabel(/I confirm creating a shared Foundry agent/).check()
    if (method === 'setItem') await create.click()
    await expect(panel.getByRole('alert')).toContainText(
      'No new request was sent',
    )
    await expect(create).toBeDisabled()
    expect(state.posts).toHaveLength(0)
  })
}

test('an acknowledged publication survives reload and blocks a stale spec in another tab', async ({
  page,
  context,
}) => {
  const state = await openCreation(page, {
    hash: '#chat',
    designerAnswer: noTemplateAnswer,
  })
  const other = await context.newPage()
  const otherState = await openCreation(other, {
    hash: '#chat',
    designerAnswer: noTemplateAnswer.replace(
      spec.instructions,
      'Use only dates from the example notice.',
    ),
  })
  const stalePanel = await openPromptReview(other)
  await stalePanel.getByLabel('Operator key', { exact: true }).fill(operatorKey)
  await stalePanel
    .getByLabel(/I confirm creating a shared Foundry agent/)
    .check()

  const panel = await openPromptReview(page)
  await panel.getByLabel('Operator key', { exact: true }).fill(operatorKey)
  await panel.getByLabel(/I confirm creating a shared Foundry agent/).check()
  state.hold = true
  await panel.getByRole('button', { name: 'Create in Foundry' }).click()
  await expect(panel).toContainText('Publishing to Foundry')
  const id = state.posts[0].idempotency_key

  await stalePanel.getByRole('button', { name: 'Create in Foundry' }).click()
  await expect(stalePanel.getByRole('alert')).toContainText(
    'Check its status first',
  )
  await expect(stalePanel).toContainText(id)
  expect(otherState.posts).toHaveLength(0)
  await other.close()

  await page.reload()
  const reopened = await openPromptReview(page)
  await reopened.getByRole('button', { name: 'Check creation status' }).click()
  await expect(reopened).toContainText('Publishing to Foundry')
  await expect(
    reopened.getByRole('button', { name: 'Finish tracking this request' }),
  ).toHaveCount(0)
  expect(state.posts).toHaveLength(1)
  state.hold = false
  await expect(reopened).toContainText('is ready in Foundry')
  expect(state.record?.id).toBe('created-' + id)
})
