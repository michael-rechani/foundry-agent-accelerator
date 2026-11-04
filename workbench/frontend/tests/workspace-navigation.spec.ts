import { expect, test } from '@playwright/test'
import { openCreation } from './helpers/creation-lab'
import { openLibrary } from './helpers/library-lab'
import { libraryNav, openChat, workspaceNav } from './helpers/navigation'

test('workspace pages update their links and support reload and Back/Forward', async ({
  page,
}) => {
  await openLibrary(page, { hash: '#chat' })
  await workspaceNav(page).getByRole('button', { name: 'All agents' }).click()
  await expect(page).toHaveURL(/#library$/)
  await libraryNav(page)
    .getByRole('button', { name: /My agents/ })
    .click()
  await expect(page).toHaveURL(/#agents$/)
  await openChat(page)
  await expect(page).toHaveURL(/#chat$/)
  await page.goBack()
  await expect(page).toHaveURL(/#agents$/)
  await expect(
    libraryNav(page).getByRole('button', { name: /My agents/ }),
  ).toHaveAttribute('aria-current', 'page')
  await page.goForward()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toBeVisible()
  await workspaceNav(page).getByRole('button', { name: 'All agents' }).click()
  await page.reload()
  await expect(page).toHaveURL(/#library$/)
  await expect(
    workspaceNav(page).getByRole('button', { name: 'All agents' }),
  ).toHaveAttribute('aria-current', 'page')
  await page.evaluate(() => {
    window.location.hash = ''
  })
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toBeVisible()
})

test('creation and browsing share one catalog load, including after a retry', async ({
  page,
}) => {
  const state = await openCreation(page, {
    hash: '#chat',
    designerAnswer: 'Tell me the job you want the agent to do.',
    templateFailure: true,
  })
  await workspaceNav(page).getByRole('button', { name: 'All agents' }).click()
  await expect(page.getByRole('alert')).toContainText(
    'Created-agent storage is unavailable',
  )
  expect(state.templateLoads).toBe(1)
  state.templateFailure = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(
    page.getByRole('heading', {
      name: 'Find an agent for the job',
      exact: true,
    }),
  ).toBeVisible()
  await page.evaluate(() => {
    window.location.hash = '#create'
  })
  await expect(
    page.getByRole('button', { name: 'Prepare setup', exact: true }),
  ).toBeVisible()
  expect(state.templateLoads).toBe(2)
  await openChat(page)
  await page.evaluate(() => {
    window.location.hash = '#create'
  })
  await expect(
    page.getByRole('button', { name: 'Prepare setup', exact: true }),
  ).toBeVisible()
  expect(state.templateLoads).toBe(2)
})

test('a Lab without creation replaces an unavailable creation link', async ({
  page,
}) => {
  await openLibrary(page, { hash: '#create', withoutCreation: true })
  await expect(page).toHaveURL(/#library$/)
  await expect(
    workspaceNav(page).getByRole('button', { name: 'All agents' }),
  ).toHaveAttribute('aria-current', 'page')
})

test('shared history loads when opened by a direct link', async ({ page }) => {
  await openCreation(page, { hash: '#history' })
  await expect(
    page.getByRole('heading', { name: 'Saved conversations', exact: true }),
  ).toBeVisible()
  await expect(
    page.getByText('No saved conversations', { exact: false }),
  ).toBeVisible()
})
