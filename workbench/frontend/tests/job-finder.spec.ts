import { expect, test } from '@playwright/test'
import { openLibrary } from './helpers/library-lab'
import { workspaceNav } from './helpers/navigation'

const finder = (page: import('@playwright/test').Page) =>
  page.getByRole('region', { name: 'Describe the job' })

test('the Lab opens on Chat and the sidebar has one agents entry', async ({
  page,
}) => {
  const state = await openLibrary(page, { hash: '' })
  await expect(
    workspaceNav(page).getByRole('button', { name: 'Chat' }),
  ).toHaveAttribute('aria-current', 'page')
  await expect(
    workspaceNav(page).getByRole('button', { name: 'Find an agent' }),
  ).toHaveCount(0)
  await expect(
    workspaceNav(page).getByRole('button', { name: /^All agents/ }),
  ).toHaveCount(1)
  await expect(page.getByRole('textbox', { name: 'Message' })).toBeVisible()
  await expect(finder(page)).toHaveCount(0)
  expect(state.chat).toHaveLength(0)
})

test('the library opens with the job finder above the agents', async ({
  page,
}) => {
  const state = await openLibrary(page, { hash: '#library' })
  await expect(
    page.getByRole('heading', { level: 1, name: 'Find an agent for the job' }),
  ).toBeVisible()
  await expect(
    finder(page).getByRole('textbox', { name: 'What are you trying to do?' }),
  ).toBeVisible()
  await expect(finder(page)).toContainText('does not use an AI model')
  await expect(
    page.getByRole('navigation', { name: 'Breadcrumb' }),
  ).toContainText(/Agent library\s*Browse/)
  expect(state.chat).toHaveLength(0)
})

test('old #start links open the library, with the finder', async ({ page }) => {
  await openLibrary(page, { hash: '#start' })
  await expect(
    workspaceNav(page).getByRole('button', { name: /^All agents/ }),
  ).toHaveAttribute('aria-current', 'page')
  await expect(finder(page)).toBeVisible()
})

test('describing a job finds a ready agent and sends nothing', async ({
  page,
}) => {
  const state = await openLibrary(page, { hash: '#library' })
  const ask = finder(page)
  await ask
    .getByRole('textbox', { name: 'What are you trying to do?' })
    .fill('check a document against a checklist')
  await ask.getByRole('button', { name: 'Find an agent' }).click()
  await expect(
    ask.getByRole('heading', { level: 3, name: /^Best matches for/ }),
  ).toBeFocused()
  await ask.getByRole('button', { name: /^Use / }).first().click()
  await expect(page.getByRole('textbox', { name: 'Message' })).toBeVisible()
  expect(state.chat).toHaveLength(0)
  expect(state.creations).toBe(0)
})

test('a job nothing matches says so and offers a way forward', async ({
  page,
}) => {
  const state = await openLibrary(page, { hash: '#library' })
  const ask = finder(page)
  await ask
    .getByRole('textbox', { name: 'What are you trying to do?' })
    .fill('zzzz qqqq')
  await ask.getByRole('button', { name: 'Find an agent' }).click()
  await expect(
    ask.getByRole('heading', { level: 3, name: /^No match found/ }),
  ).toBeVisible()
  await ask.getByRole('button', { name: 'Create an agent' }).click()
  await expect(
    page.getByRole('heading', { name: 'Create an agent', exact: true }),
  ).toBeVisible()
  expect(state.creations).toBe(0)
})

test('the finder stays on the library when creation is off', async ({
  page,
}) => {
  await openLibrary(page, { hash: '#library', withoutCreation: true })
  const ask = finder(page)
  await ask
    .getByRole('textbox', { name: 'What are you trying to do?' })
    .fill('zzzz qqqq')
  await ask.getByRole('button', { name: 'Find an agent' }).click()
  await expect(
    ask.getByRole('heading', { level: 3, name: /^No match found/ }),
  ).toBeVisible()
  await expect(
    ask.getByRole('button', { name: 'Create an agent' }),
  ).toHaveCount(0)
})
