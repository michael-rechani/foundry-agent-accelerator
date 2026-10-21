import { type Page, expect, test } from '@playwright/test'
import { guidedReview, registry } from './fixtures'
import { openWorkspace } from './helpers/chat-lab'

const caseHelper = registry.find((item) => item.id === 'case-review')!
const twoAgents = { agents: [guidedReview, caseHelper] }

// Start without stored choices, as a first-time visitor would.
test.use({ storageState: { cookies: [], origins: [] } })

const editor = (page: Page) =>
  page.getByRole('textbox', { name: 'Message', exact: true })
const choices = (page: Page) =>
  page.locator('.welcome-modes').getByRole('button')

test('chat opens clean, with no agent details, and sends nothing', async ({
  page,
}) => {
  const state = await openWorkspace(page, { config: twoAgents, startup: true })
  await expect(page.locator('.chat-welcome h1')).toHaveText(
    'What agent do you want to build?',
  )
  await expect(choices(page)).toHaveText([/Try a pre-built agent/])
  await expect(page.locator('.chat-welcome')).not.toContainText(
    guidedReview.label,
  )
  await expect(page.locator('.chat-welcome .welcome-kind')).toHaveCount(0)
  await expect(page.locator('.environment-badge')).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: 'Presenter view' }),
  ).toHaveCount(0)
  await expect(page.locator('.prompt-options')).toHaveCount(0)
  await expect(page.locator('.chat-aside')).toHaveCount(0)
  await expect(page.getByText('About this agent')).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: 'Save to shared history' }),
  ).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: /Choose an agent/ }),
  ).toBeVisible()
  await expect(editor(page)).toHaveAttribute(
    'placeholder',
    /Describe the agent you want to build/,
  )
  expect(state.requests).toEqual([])
})

test('Try a pre-built agent opens the agent picker', async ({ page }) => {
  await openWorkspace(page, { config: twoAgents, startup: true })
  await choices(page).first().click()
  await expect(page.getByPlaceholder('Search agents')).toBeVisible()
})

test('the guide and examples open inside the clean chat', async ({ page }) => {
  const state = await openWorkspace(page, { config: twoAgents, startup: true })
  const toggle = page.getByRole('button', {
    name: 'Show agent guide and examples',
  })
  await toggle.click()
  await expect(page.locator('.chat-welcome h1')).toHaveText(
    'What agent do you want to build?',
  )
  await expect(
    page.getByRole('heading', { name: 'What you can do' }),
  ).toBeVisible()
  await expect(page.getByText('About this agent')).toHaveCount(0)
  await expect(page.locator('.chat-aside')).toHaveCount(0)
  await page.getByRole('button', { name: /Help me design an agent/ }).click()
  await expect(editor(page)).toHaveValue(/Help me design an agent/)
  await page.getByRole('button', { name: 'Hide guide and examples' }).click()
  await expect(page.locator('.prompt-options')).toHaveCount(0)
  await page.reload()
  await expect(page.locator('.chat-welcome h1')).toHaveText(
    'What agent do you want to build?',
  )
  expect(state.requests).toEqual([])
})

test('a saved full view can still return to the simple view', async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem('ai-foundry-lab-simple-chat', '0'),
  )
  await openWorkspace(page, { config: twoAgents, startup: true })
  await expect(page.locator('.chat-welcome h1')).toHaveText(guidedReview.label)
  await page.getByRole('button', { name: 'Simple view' }).click()
  await expect(page.locator('.chat-welcome h1')).toHaveText(
    'What agent do you want to build?',
  )
})

const withDesigner = {
  ...twoAgents,
  library_preview: {
    enabled: true,
    reason: null,
    agent: 'lab-library-preview',
  },
}

test('a first message chats with the Agent designer and stays clean', async ({
  page,
}) => {
  const state = await openWorkspace(page, {
    config: withDesigner,
    startup: true,
    answer: 'Good morning! What would you like to build?',
  })
  await editor(page).fill('Good morning')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.assistant-message')).toContainText(
    'What would you like to build?',
  )
  expect(state.requests.map((item) => item.agent_id)).toEqual([
    'library-agent-designer',
  ])
  await expect(page.locator('.assistant-heading')).toContainText(
    'Agent designer',
  )
  await expect(page.locator('.chat-aside')).toHaveCount(0)
  await expect(page.getByText('About this agent')).toHaveCount(0)
  await expect(page.locator('.answer-details')).toHaveCount(0)
  await expect(page.locator('.review-note')).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: /Agent designer/ }).first(),
  ).toBeVisible()
  await expect(editor(page)).toHaveAttribute('placeholder', 'Reply...')
  await expect(
    page.getByRole('button', { name: 'Continue in a new chat' }),
  ).toHaveCount(0)
  await expect(page.locator('.save-state')).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: /Choose an agent/ }),
  ).toHaveCount(0)
})

test('the Agent designer can end with a downloadable agent spec', async ({
  page,
}) => {
  const spec = {
    name: 'Renewal Checklist Helper',
    summary: 'Turns a renewal notice into a short checklist.',
    instructions: 'List what the person must send before the renewal date.',
    inputs: 'A renewal notice',
    outputs: 'A checklist',
    tools_needed: [],
    human_decision: 'A caseworker decides eligibility.',
    closest_template: null,
  }
  await openWorkspace(page, {
    config: withDesigner,
    startup: true,
    answer: `Here is the idea.\n\n\`\`\`agent-spec\n${JSON.stringify(spec)}\n\`\`\`\n`,
  })
  await editor(page).fill('Help people renew benefits')
  await page.getByRole('button', { name: 'Send message' }).click()
  const card = page.getByRole('region', { name: 'Agent spec' })
  await expect(card).toContainText('Renewal Checklist Helper')
  await expect(card).toContainText('A caseworker decides eligibility.')
  await expect(page.locator('.assistant-message')).not.toContainText(
    'agent-spec',
  )
  await expect(page.locator('.assistant-message')).not.toContainText(
    '"instructions"',
  )
  await expect(card.getByRole('button', { name: /Create agent/ })).toHaveCount(
    0,
  )
  const download = page.waitForEvent('download')
  await card.getByRole('button', { name: 'Download agent spec' }).click()
  const file = await download
  expect(file.suggestedFilename()).toBe(
    'renewal-checklist-helper.foundry-agent.json',
  )
})

test('from the Agent designer the person can move to a real agent', async ({
  page,
}) => {
  const state = await openWorkspace(page, {
    config: withDesigner,
    startup: true,
  })
  await editor(page).fill('Hello')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.assistant-message')).toBeVisible()
  await page.locator('.agent-picker').click()
  const picker = page.getByRole('dialog', { name: 'Choose an agent' })
  await expect(
    picker.getByRole('region', { name: 'General chat' }),
  ).toContainText('Agent designer')
  await picker
    .getByRole('button', { name: new RegExp(caseHelper.label) })
    .click()
  await page.getByRole('button', { name: 'Switch agent' }).click()
  await editor(page).fill('Review synthetic APP-1')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.chat-aside')).toBeVisible()
  expect(state.requests.map((item) => item.agent_id)).toEqual([
    'library-agent-designer',
    caseHelper.id,
  ])
})

test('without library previews the first message goes to the default agent', async ({
  page,
}) => {
  const state = await openWorkspace(page, { config: twoAgents, startup: true })
  await editor(page).fill('Good morning')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.assistant-message')).toBeVisible()
  expect(state.requests.map((item) => item.agent_id)).toEqual([guidedReview.id])
})
