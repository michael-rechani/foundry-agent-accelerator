import { expect, type Page } from '@playwright/test'

export const workspaceNav = (page: Page) =>
  page.getByRole('navigation', { name: 'Workspace' })

export const libraryNav = (page: Page) =>
  page.getByRole('navigation', { name: 'Agent library' })

export const hoodSwitch = (page: Page) =>
  page.getByRole('switch', { name: /Under the hood/ })

export const waitForLab = (page: Page) =>
  expect(workspaceNav(page)).toBeVisible()

export const openChat = (page: Page) =>
  workspaceNav(page).getByRole('button', { name: 'Chat', exact: true }).click()

// The library tabs live under "All agents" in the workspace navigation.
export async function openLibraryTab(page: Page, name: string | RegExp) {
  await workspaceNav(page).getByRole('button', { name: 'All agents' }).click()
  await libraryNav(page).getByRole('button', { name }).click()
}

// Follows an in-app link the way a click on a saved link would.
export const followLink = (page: Page, hash: string) =>
  page.evaluate((link) => {
    window.location.hash = link
  }, hash)
