import { type Page, expect, test } from '@playwright/test'
import { guidedReview, registry } from './fixtures'
import { openWorkspace } from './helpers/chat-lab'

const caseHelper = registry.find((item) => item.id === 'case-review')!
const twoAgents = { agents: [guidedReview, caseHelper] }

const editor = (page: Page) =>
  page.getByRole('textbox', { name: 'Message', exact: true })
const modes = (page: Page) => page.locator('.welcome-modes')
const mode = (page: Page, name: string) =>
  modes(page).getByRole('button', { name })

test('the welcome offers three ways to start and sends nothing', async ({
  page,
}) => {
  const state = await openWorkspace(page, { config: twoAgents })
  await expect(modes(page).getByRole('button')).toHaveText([
    /Ask anything/,
    /What can I create\?/,
    /Switch agent/,
  ])
  await expect(mode(page, /Switch agent/)).toBeEnabled()
  expect(state.requests).toEqual([])
})

test('Ask anything puts the cursor in the message box', async ({ page }) => {
  await openWorkspace(page, { config: twoAgents })
  await mode(page, /Ask anything/).click()
  await expect(editor(page)).toBeFocused()
  await expect(editor(page)).toHaveValue('')
})

test('What can I create? shows the Lab guide in place, with no model call', async ({
  page,
}) => {
  const state = await openWorkspace(page, { config: twoAgents })
  const toggle = mode(page, /What can I create\?/)
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-expanded', 'true')
  const guide = page.getByRole('region', { name: 'What can I create?' })
  await expect(guide).toContainText('Agents you can use')
  await expect(guide).toContainText(guidedReview.label)
  await expect(editor(page)).toHaveValue('')
  expect(state.requests).toEqual([])

  await toggle.click()
  await expect(guide).toHaveCount(0)
})

test('choosing an agent from What can I create? starts a chat with it', async ({
  page,
}) => {
  await openWorkspace(page, { config: twoAgents })
  await mode(page, /What can I create\?/).click()
  await page.getByRole('button', { name: `Use ${caseHelper.label}` }).click()
  await expect(page.locator('.agent-picker .agent-name')).toHaveText(
    caseHelper.label,
  )
})

test('Switch agent opens the agent list and a pick changes the agent', async ({
  page,
}) => {
  await openWorkspace(page, { config: twoAgents })
  await mode(page, /Switch agent/).click()
  const list = page.getByRole('dialog', { name: 'Choose an agent' })
  await expect(list).toBeVisible()
  await expect(list.getByRole('searchbox')).toBeFocused()
  await list.getByRole('button', { name: new RegExp(caseHelper.label) }).click()
  await expect(page.locator('.agent-picker .agent-name')).toHaveText(
    caseHelper.label,
  )
  await expect(list).toHaveCount(0)
})

test('the choices step aside once the box has typed text and return when it is empty', async ({
  page,
}) => {
  await openWorkspace(page, { config: twoAgents })
  await mode(page, /What can I create\?/).click()
  await editor(page).fill('Fictional text I typed myself')
  await expect(modes(page)).toHaveCount(0)
  await expect(page.locator('.welcome-create')).toHaveCount(0)

  await editor(page).fill('')
  await expect(modes(page)).toBeVisible()
})
