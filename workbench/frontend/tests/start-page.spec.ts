import { expect, test } from '@playwright/test'
import { openLibrary } from './helpers/library-lab'
import { workspaceNav } from './helpers/navigation'

const askWhich = 'Which agent should I use or build?'

test('the Lab opens on Ask the Lab before any agent', async ({ page }) => {
  const state = await openLibrary(page, { hash: '' })
  await expect(
    page.getByRole('heading', { level: 1, name: 'Welcome to the Lab' }),
  ).toBeVisible()
  const ask = page.getByRole('region', { name: 'Ask the Lab' })
  await expect(ask).toBeVisible()
  await expect(ask.getByRole('button', { name: askWhich })).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'Message' })).toHaveCount(0)
  await expect(
    workspaceNav(page).getByRole('button', { name: 'Ask the Lab' }),
  ).toHaveAttribute('aria-current', 'page')
  await expect(
    page.getByRole('navigation', { name: 'Breadcrumb' }),
  ).toContainText(/Start here\s*Ask the Lab/)
  expect(state.chat).toHaveLength(0)
})

test('#start opens the same first page', async ({ page }) => {
  await openLibrary(page, { hash: '#start' })
  await expect(
    page.getByRole('heading', { level: 1, name: 'Welcome to the Lab' }),
  ).toBeVisible()
})

test('a question on the first page is answered without sending anything', async ({
  page,
}) => {
  const state = await openLibrary(page, { hash: '' })
  const ask = page.getByRole('region', { name: 'Ask the Lab' })
  await ask.getByRole('button', { name: askWhich }).click()
  await expect(
    ask.getByRole('heading', { level: 3, name: 'Agents you can use' }),
  ).toBeFocused()
  await expect(ask).toContainText('Nothing is sent or saved.')
  await expect(ask.getByText('In use now')).toHaveCount(0)
  expect(state.chat).toHaveLength(0)
  expect(state.drafts).toBe(0)
  expect(state.creations).toBe(0)
})

test('Try an agent opens the agent list', async ({ page }) => {
  await openLibrary(page, { hash: '' })
  await page.getByRole('button', { name: /^Try an agent/ }).click()
  await expect(
    page.getByRole('navigation', { name: 'Breadcrumb' }),
  ).toContainText(/Agent library\s*Ready to chat/)
})

test('Build your own opens agent creation when it is on', async ({ page }) => {
  const state = await openLibrary(page, { hash: '' })
  await page.getByRole('button', { name: /^Build your own/ }).click()
  await expect(
    page.getByRole('heading', { name: 'Create an agent', exact: true }),
  ).toBeVisible()
  expect(state.creations).toBe(0)
})

test('Build your own opens the library when creation is off', async ({
  page,
}) => {
  await openLibrary(page, { hash: '', withoutCreation: true })
  await expect(
    page.getByText('Browse the agent library for a starting point.'),
  ).toBeVisible()
  await page.getByRole('button', { name: /^Build your own/ }).click()
  await expect(
    workspaceNav(page).getByRole('button', { name: /^All agents/ }),
  ).toHaveAttribute('aria-current', 'page')
})

test('deep links to other pages still open them', async ({ page }) => {
  await openLibrary(page, { hash: '#library' })
  await expect(
    workspaceNav(page).getByRole('button', { name: /^All agents/ }),
  ).toHaveAttribute('aria-current', 'page')
})
