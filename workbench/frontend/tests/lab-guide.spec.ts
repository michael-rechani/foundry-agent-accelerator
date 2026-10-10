import { expect, test, type Page } from '@playwright/test'
import { addOnGroupLabels, addOns } from '../src/add-on-catalog'
import { registry } from './fixtures'
import { openWorkspace } from './helpers/chat-lab'
import { openLibrary } from './helpers/library-lab'
import { openChat } from './helpers/navigation'

const askWhich = 'Which agent should I use or build?'
const askHow = 'How is an agent built, and what can I add?'

const guide = (page: Page) => page.getByRole('region', { name: 'Ask the Lab' })

test('the welcome offers two questions to ask the Lab and shows no answer until one is chosen', async ({
  page,
}) => {
  await openWorkspace(page, { config: { agents: registry } })
  const ask = guide(page)
  await expect(ask).toBeVisible()
  for (const question of [askWhich, askHow])
    await expect(ask.getByRole('button', { name: question })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
  await expect(page.locator('.lab-guide-exchange')).toHaveCount(0)
})

test('asking which agent to use lists the ready agents and sends nothing', async ({
  page,
}) => {
  const state = await openWorkspace(page, {
    config: { agents: registry, default_agent: registry[0].id },
  })
  const ask = guide(page)
  await page.getByRole('textbox', { name: 'Message' }).fill('My own draft')
  await ask.getByRole('button', { name: askWhich }).click()

  await expect(ask.getByRole('button', { name: askWhich })).toHaveAttribute(
    'aria-expanded',
    'true',
  )
  await expect(ask.locator('.lab-guide-bubble')).toHaveText(askWhich)
  const heading = ask.getByRole('heading', {
    level: 3,
    name: 'Agents you can use',
  })
  await expect(heading).toBeFocused()
  const rows = ask.locator('.lab-guide-agents li')
  await expect(rows).toHaveCount(registry.length)
  for (const [index, item] of registry.entries()) {
    await expect(rows.nth(index)).toContainText(item.label)
    await expect(rows.nth(index)).toContainText(item.description)
  }
  await expect(rows.first()).toContainText('In use now')
  await expect(rows.first().getByRole('button')).toHaveCount(0)
  await expect(ask).toContainText(
    "Agent creation isn't turned on in this Lab, so only these agents are available.",
  )
  await expect(
    ask.getByRole('button', { name: 'Create an agent' }),
  ).toHaveCount(0)
  await expect(ask).toContainText('Nothing is sent or saved.')

  await expect(page.getByRole('textbox', { name: 'Message' })).toHaveValue(
    'My own draft',
  )
  expect(state.requests).toHaveLength(0)
  expect(state.saves).toHaveLength(0)

  await ask.getByRole('button', { name: askWhich }).click()
  await expect(page.locator('.lab-guide-exchange')).toHaveCount(0)
})

test('choosing another agent from the answer starts a chat with it', async ({
  page,
}) => {
  const state = await openWorkspace(page, {
    config: { agents: registry, default_agent: registry[0].id },
  })
  const ask = guide(page)
  await ask.getByRole('button', { name: askWhich }).click()
  await ask.getByRole('button', { name: `Use ${registry[2].label}` }).click()
  await expect(
    page.getByRole('heading', { level: 1, name: registry[2].label }),
  ).toBeVisible()
  await expect(page.locator('.agent-picker')).toContainText(registry[2].label)
  await expect(page.locator('.lab-guide-exchange')).toHaveCount(0)
  expect(state.requests).toHaveLength(0)
  expect(state.saves).toHaveLength(0)
})

test('asking how an agent is built explains the parts and groups the add-ons', async ({
  page,
}) => {
  const state = await openWorkspace(page, {
    config: { agents: registry, default_agent: registry[0].id },
  })
  const ask = guide(page)
  await ask.getByRole('button', { name: askHow }).click()

  await expect(ask.locator('.lab-guide-bubble')).toHaveText(askHow)
  await expect(
    ask.getByRole('heading', { level: 3, name: 'How an agent is built' }),
  ).toBeFocused()
  await expect(ask).toContainText(
    'instructions, a model that does the thinking, and the tools',
  )
  await expect(ask).toContainText(registry[0].guidance!.delegation)
  await expect(ask).toContainText('Chatting never changes an agent.')
  await expect(ask.getByRole('heading', { level: 4 })).toHaveText([
    addOnGroupLabels.abilities,
    addOnGroupLabels.support,
  ])
  await expect(ask.locator('.lab-guide-group li strong')).toHaveText(
    [...addOns]
      .sort(
        (a, b) =>
          (a.group === 'support' ? 1 : 0) - (b.group === 'support' ? 1 : 0),
      )
      .map((item) => item.name),
  )
  const support = ask.locator('.lab-guide-group').nth(1)
  await expect(support.locator('li strong')).toHaveText([
    'Conversation memory',
    'Document storage',
    'Response cache',
  ])
  await expect(ask.locator('.lab-guide-status')).toHaveCount(addOns.length)
  await expect(ask.getByText('Sample pilot')).toHaveCount(1)
  await expect(ask.getByText('Not available yet')).toHaveCount(
    addOns.length - 1,
  )
  await expect(ask).toContainText('Nothing here turns anything on')
  expect(state.requests).toHaveLength(0)
  expect(state.saves).toHaveLength(0)
})

test('the add-on answer links to the Add-ons page', async ({ page }) => {
  await openWorkspace(page, { config: { agents: registry } })
  const ask = guide(page)
  await ask.getByRole('button', { name: askHow }).click()
  await ask
    .getByRole('button', { name: 'See what each add-on would cost and need' })
    .click()
  await expect(
    page.getByRole('heading', { level: 1, name: 'Add-ons an agent could use' }),
  ).toBeVisible()
})

test('when agent creation is on, the answer offers it and nothing is made', async ({
  page,
}) => {
  const state = await openLibrary(page)
  await openChat(page)
  const ask = guide(page)
  await ask.getByRole('button', { name: askWhich }).click()
  await expect(ask).toContainText('start a new agent from a template')
  await expect(ask).not.toContainText("Agent creation isn't turned on")
  await ask.getByRole('button', { name: 'Create an agent' }).click()
  await expect(
    page.getByRole('heading', { name: 'Create an agent', exact: true }),
  ).toBeVisible()
  expect(state.chat).toHaveLength(0)
  expect(state.drafts).toBe(0)
  expect(state.creations).toBe(0)
})
