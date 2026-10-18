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
    'What would you like to do?',
  )
  await expect(choices(page)).toHaveText([
    /Try a new agent/,
    /Chat about an agent I'm building/,
  ])
  await expect(page.locator('.chat-welcome')).not.toContainText(
    guidedReview.label,
  )
  await expect(page.locator('.welcome-kind')).toHaveCount(0)
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

test('Chat about an agent I am building puts the cursor in the message box', async ({
  page,
}) => {
  await openWorkspace(page, { config: twoAgents, startup: true })
  await choices(page).nth(1).click()
  await expect(editor(page)).toBeFocused()
  await expect(editor(page)).toHaveValue('')
})

test('Try a new agent opens the agent picker', async ({ page }) => {
  await openWorkspace(page, { config: twoAgents, startup: true })
  await choices(page).first().click()
  await expect(page.getByPlaceholder('Search agents')).toBeVisible()
})

test('the agent guide and examples come back and the choice is remembered', async ({
  page,
}) => {
  await openWorkspace(page, { config: twoAgents, startup: true })
  await page
    .getByRole('button', { name: 'Show agent guide and examples' })
    .click()
  await expect(page.locator('.chat-welcome h1')).toHaveText(guidedReview.label)
  await expect(
    page.getByRole('heading', { name: 'About this agent' }),
  ).toBeVisible()
  await page.reload()
  await expect(page.locator('.chat-welcome h1')).toHaveText(guidedReview.label)
  await page.getByRole('button', { name: 'Simple view' }).click()
  await expect(page.locator('.chat-welcome h1')).toHaveText(
    'What would you like to do?',
  )
})
