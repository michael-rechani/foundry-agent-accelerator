import { type Page, expect, test } from '@playwright/test'
import { guidedReview, registry } from './fixtures'
import { support } from './helpers/catalog'
import { openWorkspace, send } from './helpers/chat-lab'
import { openAgent, openLibrary } from './helpers/library-lab'
import { libraryNav, openChat, workspaceNav } from './helpers/navigation'

const caseHelper = registry.find((item) => item.id === 'case-review')!
const twoAgents = { agents: [guidedReview, caseHelper] }

const picker = (page: Page) => page.locator('.agent-picker')
const pickerName = (page: Page) => picker(page).locator('.agent-name')
const editor = (page: Page) =>
  page.getByRole('textbox', { name: 'Message', exact: true })
const confirmation = (page: Page, name: string) =>
  page.getByRole('dialog', { name })
const anyConfirmation = (page: Page) => page.locator('dialog.confirm-dialog')
const examples = (page: Page) => page.locator('.prompt-options button')

async function choose(page: Page, label: string) {
  await picker(page).click()
  await page
    .getByRole('dialog', { name: 'Choose an agent' })
    .getByRole('button', { name: new RegExp(label) })
    .click()
}

test('switching agents says what will happen and waits for a yes', async ({
  page,
}) => {
  await openWorkspace(page, { config: twoAgents })
  const draft = 'Fictional notes I typed myself'
  await editor(page).fill(draft)

  await choose(page, caseHelper.label)
  const dialog = confirmation(page, `Switch to ${caseHelper.label}?`)
  await expect(dialog).toContainText('Switching agents starts a new chat.')
  await expect(dialog).toContainText('Your unsaved draft will be cleared.')
  await expect(dialog).toContainText("Saved history isn't deleted.")
  await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused()

  // Escape and Cancel both leave the chat as it was and return to the picker.
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(picker(page)).toBeFocused()
  await expect(pickerName(page)).toHaveText(guidedReview.label)
  await expect(editor(page)).toHaveValue(draft)

  await choose(page, caseHelper.label)
  await dialog.getByRole('button', { name: 'Cancel' }).click()
  await expect(dialog).toHaveCount(0)
  await expect(picker(page)).toBeFocused()
  await expect(pickerName(page)).toHaveText(guidedReview.label)
  await expect(editor(page)).toHaveValue(draft)

  await choose(page, caseHelper.label)
  await dialog.getByRole('button', { name: 'Switch agent' }).click()
  await expect(dialog).toHaveCount(0)
  await expect(pickerName(page)).toHaveText(caseHelper.label)
  await expect(editor(page)).toHaveValue('')
  await expect(
    page.getByRole('heading', { name: caseHelper.label, exact: true }),
  ).toBeVisible()
})

test('a conversation asks before switching until it is saved', async ({
  page,
}) => {
  await openWorkspace(page, { config: twoAgents })
  await send(page)
  await choose(page, caseHelper.label)
  const dialog = confirmation(page, `Switch to ${caseHelper.label}?`)
  await expect(dialog).toContainText(
    'Your unsaved conversation will be cleared.',
  )
  await dialog.getByRole('button', { name: 'Cancel' }).click()
  await expect(pickerName(page)).toHaveText(guidedReview.label)

  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect(
    page.getByText('Saved / shared', { exact: true }).filter({ visible: true }),
  ).toBeVisible()
  await choose(page, caseHelper.label)
  await expect(anyConfirmation(page)).toHaveCount(0)
  await expect(pickerName(page)).toHaveText(caseHelper.label)
})

test('an example nobody edited is replaced without a prompt', async ({
  page,
}) => {
  await openWorkspace(page, { config: twoAgents })
  await page
    .getByRole('button', { name: guidedReview.prompts[0].label, exact: true })
    .click()
  await expect(editor(page)).toHaveValue(guidedReview.prompts[0].text)
  await choose(page, caseHelper.label)
  await expect(anyConfirmation(page)).toHaveCount(0)
  await expect(pickerName(page)).toHaveText(caseHelper.label)
  await expect(editor(page)).toHaveValue('')
})

test('choosing the current agent just returns to its chat', async ({
  page,
}) => {
  await openWorkspace(page, { config: twoAgents })
  await editor(page).fill('Fictional draft that stays put')
  await choose(page, guidedReview.label)
  await expect(anyConfirmation(page)).toHaveCount(0)
  await expect(pickerName(page)).toHaveText(guidedReview.label)
  await expect(editor(page)).toHaveValue('Fictional draft that stays put')
})

test('New chat asks only when something would be lost', async ({ page }) => {
  await openWorkspace(page, { config: twoAgents })
  const newChat = page.getByRole('button', { name: 'New chat', exact: true })
  await newChat.click()
  await expect(anyConfirmation(page)).toHaveCount(0)

  await editor(page).fill('Fictional draft')
  await newChat.click()
  const dialog = confirmation(page, 'Start a new chat?')
  await expect(dialog).toContainText('Your unsaved draft will be cleared.')
  await dialog.getByRole('button', { name: 'Cancel' }).click()
  await expect(newChat).toBeFocused()
  await expect(editor(page)).toHaveValue('Fictional draft')

  await newChat.click()
  await dialog.getByRole('button', { name: 'Start new chat' }).click()
  await expect(editor(page)).toHaveValue('')
  await expect(pickerName(page)).toHaveText(guidedReview.label)
})

test('examples step aside once the box has typed text, and stay while it holds an example', async ({
  page,
}) => {
  await openWorkspace(page, { config: twoAgents })
  const welcome = page.locator('.chat-welcome')
  await expect(examples(page)).toHaveCount(guidedReview.prompts.length)
  await expect(welcome).toContainText('Pick an example to fill the message box')

  await editor(page).fill('Fictional text I typed myself')
  await expect(examples(page)).toHaveCount(0)
  await expect(welcome).toContainText('Nothing is sent until you press Send.')

  await editor(page).fill('')
  await expect(examples(page)).toHaveCount(guidedReview.prompts.length)

  await examples(page).nth(1).click()
  await expect(editor(page)).toHaveValue(guidedReview.prompts[1].text)
  await expect(examples(page)).toHaveCount(guidedReview.prompts.length)
  await expect(examples(page).nth(1)).toHaveAttribute('aria-pressed', 'true')
  await expect(welcome).toContainText('Your example is in the message box')

  await examples(page).nth(0).click()
  await expect(editor(page)).toHaveValue(guidedReview.prompts[0].text)
  await expect(examples(page).nth(0)).toHaveAttribute('aria-pressed', 'true')
  await expect(examples(page).nth(1)).toHaveAttribute('aria-pressed', 'false')

  await editor(page).fill(guidedReview.prompts[0].text + ' Edited.')
  await expect(examples(page)).toHaveCount(0)
})
test('All agents opens the full list, but library tabs keep the agent you were reading', async ({
  page,
}) => {
  await openLibrary(page)
  const tabs = libraryNav(page)
  const agentPage = page.getByRole('heading', {
    level: 1,
    name: support.label,
    exact: true,
  })
  const list = page.getByRole('heading', {
    level: 1,
    name: 'Find an agent for the job',
  })
  await openAgent(page, support.label)

  await tabs.getByRole('button', { name: /^Ready to chat/ }).click()
  await tabs.getByRole('button', { name: 'Browse' }).click()
  await expect(agentPage).toBeVisible()

  await openChat(page)
  await workspaceNav(page)
    .getByRole('button', { name: /^All agents/ })
    .click()
  await expect(list).toBeVisible()
  await expect(agentPage).toHaveCount(0)
})
