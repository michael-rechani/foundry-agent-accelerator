import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { agent, openSteps, openWorkspace, send } from './helpers/chat-lab'
import { expectFitsViewport } from './helpers/layout'
import { workspaceNav } from './helpers/navigation'

test('shared lab details are available on demand across workspace views', async ({
  page,
}, testInfo) => {
  await openWorkspace(page, { config: { reviews_enabled: true } })
  const control = page.getByTitle('About this shared lab', { exact: true })
  const notice = page.getByRole('complementary', { name: 'Shared lab details' })
  for (const name of ['Chat', 'Shared history', 'All agents', 'Performance']) {
    await workspaceNav(page).getByTitle(name, { exact: true }).click()
    // The top bar names the page only in its breadcrumb, never as a title.
    await expect(
      page
        .getByRole('banner')
        .getByText(name, { exact: true })
        .and(page.locator(':not(.topbar-crumbs *)')),
    ).toHaveCount(0)
    await expect(control).toBeInViewport()
    await expect(notice).toBeHidden()
    await expect(
      page.getByRole('complementary', { name: 'Lab data boundary' }),
    ).toHaveCount(0)
    await control.click()
    await expect(notice).toBeInViewport()
    await expect(notice).toContainText(
      'No user sign-in. Saved records are shared.',
    )
    await expect(notice).toContainText('Use sample data only.')
    await expect(notice).toContainText(
      'read, modify and delete saved chats, and read reviews and add requested evidence',
    )
    expect(
      await notice.evaluate((element) => {
        const { left, right } = element.getBoundingClientRect()
        return left >= 0 && right <= innerWidth
      }),
    ).toBe(true)
    if (name === 'Chat') {
      await page.evaluate(() => document.fonts.ready)
      await page.screenshot({
        path: testInfo.outputPath('shared-lab-details.png'),
      })
      await control.press('Enter')
      await expect(notice).toBeHidden()
      await control.press('Space')
      await expect(notice).toBeVisible()
    }
  }
})

test('shared lab details fit narrow screens and close with Escape', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 720 })
  await openWorkspace(page, {
    config: {
      agents: [
        {
          ...agent,
          label: 'Customer application and supporting evidence review',
        },
      ],
    },
  })
  await expectFitsViewport(page)
  await expect(
    page.getByRole('complementary', { name: 'Lab data boundary' }),
  ).toHaveCount(0)
  await expect(
    page.getByRole('button', {
      name: 'Customer application and supporting evidence review',
    }),
  ).toBeInViewport()
  const control = page.getByTitle('About this shared lab', { exact: true })
  const notice = page.getByRole('complementary', { name: 'Shared lab details' })
  await control.focus()
  await control.press('Enter')
  await expect(notice).toBeInViewport()
  expect(
    await notice.evaluate((element) => {
      const { left, right } = element.getBoundingClientRect()
      return left >= 0 && right <= innerWidth
    }),
  ).toBe(true)
  await control.press('Escape')
  await expect(notice).toBeHidden()
  await expect(control).toBeFocused()
})

test('disconnected preview does not claim connected shared storage', async ({
  page,
}) => {
  await openWorkspace(page, { preview: true })
  await expect(
    page.getByTitle('About this shared lab', { exact: true }),
  ).toHaveCount(0)
  await expect(
    page.getByRole('complementary', { name: 'Shared lab details' }),
  ).toHaveCount(0)
  await expect(page.getByText('Local preview', { exact: true })).toBeVisible()
  await expect(page.locator('.chat-welcome .welcome-hint')).toContainText(
    'No model calls or saved records',
  )
  await expect(
    page.getByRole('complementary', { name: 'Lab data boundary' }),
  ).toHaveCount(0)
})

test('save, reopen, follow up, update and delete shared history', async ({
  page,
}) => {
  const state = await openWorkspace(page)
  await send(page)
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect(
    page.getByText('Saved / shared', { exact: true }).filter({ visible: true }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'New chat', exact: true }).click()
  await page.getByRole('button', { name: /^Shared history/ }).click()
  await page.locator('.saved-open').click()
  const storedSteps = await openSteps(page)
  await expect(storedSteps.locator('.answer-step-state')).toHaveText([
    'Saved earlier',
  ])
  await expect(storedSteps.getByText('Confirmed', { exact: true })).toHaveCount(
    0,
  )
  await page.locator('.receipt-details > summary').click()
  await expect(
    page.locator('.receipt').getByText('Stored / not reverified'),
  ).toBeVisible()
  await expect(page.getByText('Verified receipt', { exact: true })).toHaveCount(
    0,
  )
  await send(page, 'What evidence is missing?')
  expect(state.requests[1].history.map((message) => message.role)).toEqual([
    'user',
    'assistant',
  ])
  expect(state.requests[1].thread).not.toBe(state.requests[0].thread)
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect(
    page.getByText('Saved / shared', { exact: true }).filter({ visible: true }),
  ).toBeVisible()
  expect(state.updates).toEqual(['v1'])
  expect(state.saves[1].turns.every((turn) => !('stored' in turn))).toBeTruthy()
  await page.getByRole('button', { name: 'New chat', exact: true }).click()
  await page.getByRole('button', { name: /^Shared history/ }).click()
  await page
    .getByRole('button', { name: 'Delete Review synthetic APP-1' })
    .click()
  const confirm = page.getByRole('dialog', {
    name: 'Delete this saved conversation?',
  })
  await expect(confirm).toContainText('removed from shared history')
  await confirm.getByRole('button', { name: 'Delete for everyone' }).click()
  await expect(page.getByText('No saved conversations')).toBeVisible()
  expect(state.deletes).toEqual(['v2'])
})

test('conflicting save preserves local replies and allows export', async ({
  page,
}) => {
  const state = await openWorkspace(page, { conflict: true })
  await send(page)
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect(
    page.getByText('Saved / shared', { exact: true }).filter({ visible: true }),
  ).toBeVisible()
  await send(page, 'Keep this local follow-up')
  expect(state.requests[1].thread).toBe(state.requests[0].thread)
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect(page.getByRole('status')).toContainText(
    'changed in another browser',
  )
  await expect(
    page.getByText('Keep this local follow-up', { exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Export conversation' }),
  ).toBeEnabled()
  await expect(
    page
      .getByText('Unsaved changes', { exact: true })
      .filter({ visible: true }),
  ).toBeVisible()
})

test('history timeout releases controls without losing the draft', async ({
  page,
}) => {
  await page.clock.install()
  await openWorkspace(page, { stalledHistory: true })
  await page.getByRole('textbox', { name: 'Message' }).fill('Keep this draft')
  await page.getByRole('button', { name: /^Shared history/ }).click()
  await expect(page.getByText('Loading history...')).toBeVisible()
  await page.clock.runFor(45001)
  await expect(page.getByRole('status')).toContainText(
    'History request stopped',
  )
  await page.getByRole('button', { name: 'Chat', exact: true }).click()
  await expect(page.getByRole('textbox', { name: 'Message' })).toHaveValue(
    'Keep this draft',
  )
  await expect(page.getByRole('button', { name: 'Send message' })).toBeEnabled()
})

test('draft export includes unsent text and reload warns', async ({ page }) => {
  await openWorkspace(page)
  const editor = page.getByRole('textbox', { name: 'Message' })
  await editor.fill('Unsent synthetic draft')
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export conversation' }).click()
  const download = await downloadPromise
  const payload = JSON.parse(await readFile((await download.path())!, 'utf8'))
  expect(payload.draft).toBe('Unsent synthetic draft')
  const dialogPromise = page.waitForEvent('dialog')
  void page.reload().catch(() => null)
  const dialog = await dialogPromise
  expect(dialog.type()).toBe('beforeunload')
  await dialog.dismiss()
  await expect(editor).toHaveValue('Unsent synthetic draft')
})
