import { expect, test } from '@playwright/test'
import { docsScreenshot, screenshot } from './fixtures'
import { expectFitsViewport } from './helpers/layout'
import { workspaceNav } from './helpers/navigation'
import { create, interrupt, openReviews } from './helpers/reviews-lab'

test('interrupted recovery requires consent, uses saved input and preserves history', async ({
  page,
}, testInfo) => {
  const state = await interrupt(page)
  const original = structuredClone(state.document!.runs[0])
  await expect(page.locator('.review-next-step')).toContainText(
    'recovery may incur another model charge',
  )
  await page.getByRole('button', { name: 'Refresh reviews' }).click()
  expect(state.recoveries).toBe(0)
  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('may incur another model charge')
    await dialog.dismiss()
  })
  await page.getByRole('button', { name: 'Recover review' }).click()
  expect(state.executions).toBe(1)
  expect(state.document!.runs).toEqual([original])
  await page.screenshot({
    path: testInfo.outputPath('review-recovery.png'),
    fullPage: true,
  })
  await expectFitsViewport(page)
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Recover review' }).click()
  await expect(page.getByText('Running', { exact: true })).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Recover review' }),
  ).toHaveCount(0)
  expect(state.recoveries).toBe(1)
  expect(state.document!.runs[0]).toEqual(original)
  expect(state.document!.runs[1].input).toEqual(original.input)
  expect(state.document!.runs[1].resumed_from).toBe(original.id)
  state.runningReads = 0
  await expect(page.getByText('Results saved', { exact: true })).toBeVisible()
  await page.reload()
  await page.getByRole('tab', { name: 'Run details' }).click()
  await expect(
    page.getByText('Recovery requested using saved input'),
  ).toBeVisible()
  await page.getByLabel('Run version').selectOption('0')
  await expect(page.getByText('Run error: execution_interrupted')).toBeVisible()
  expect(state.executions).toBe(2)
})

test('recovery conflicts preserve input and never silently resubmit', async ({
  page,
}) => {
  const state = await interrupt(page)
  const original = structuredClone(state.document)
  state.conflict = true
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Recover review' }).click()
  await expect(
    page.getByRole('alert').filter({ hasText: 'This review changed' }),
  ).toBeVisible()
  expect(state.document).toEqual(original)
  await page.getByRole('button', { name: 'Refresh reviews' }).click()
  expect(state.recoveries).toBe(0)
  expect(state.executions).toBe(1)
})

test('recovery is unavailable after the four-run limit or a saved failure', async ({
  page,
}) => {
  const state = await interrupt(page)
  state.document!.runs = Array.from({ length: 4 }, (_, index) => ({
    ...structuredClone(state.document!.runs[0]),
    id: `run-${index + 1}`,
  }))
  await page.getByRole('button', { name: 'Refresh reviews' }).click()
  await expect(page.locator('.review-next-step')).toContainText(
    'four-run limit has been reached',
  )
  await expect(
    page.getByRole('button', { name: 'Recover review' }),
  ).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: 'Export review' }),
  ).toBeEnabled()
  state.document!.status = 'failed'
  state.document!.runs = state.document!.runs.slice(0, 1)
  await page.getByRole('button', { name: 'Refresh reviews' }).click()
  await expect(
    page.getByRole('button', { name: 'Recover review' }),
  ).toHaveCount(0)
  expect(state.recoveries).toBe(0)
})

test('review, inspect evidence, clarify, resume, reopen and preserve snapshots', async ({
  page,
}, testInfo) => {
  const state = await openReviews(page)
  await create(page)
  await expect(page.locator('.review-next-step')).toContainText(
    'Checklist and documents saved; no results yet',
  )
  expect(state.executions).toBe(0)
  await page.getByRole('button', { name: 'Run review', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'More information needed' }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Document 1' }).click()
  await expect(
    page.getByRole('complementary', { name: 'Original text' }),
  ).toContainText('Twelve weekly workshops')
  await page.getByRole('tab', { name: 'Results' }).click()
  await expect(page.locator('.review-disclaimer')).toContainText(
    'they do not prove those documents are true',
  )
  await expect(page.locator('.review-disclaimer')).toContainText(
    'They do not approve applications or make business decisions',
  )
  await docsScreenshot(page, testInfo, 'review-findings.png')
  await page.emulateMedia({ colorScheme: 'dark' })
  await docsScreenshot(page, testInfo, 'review-findings-dark.png')
  await page.emulateMedia({ colorScheme: 'light' })
  await page
    .getByLabel('More information', { exact: true })
    .fill('Budget: $100.')
  await page.getByRole('button', { name: 'Save added information' }).click()
  expect(state.executions).toBe(1)
  await expect(page.locator('.review-next-step')).toContainText(
    'saved but not checked yet',
  )
  await page.getByRole('tab', { name: 'Original text', exact: true }).click()
  await page.getByLabel('Document', { exact: true }).selectOption('SRC-2')
  await expect(
    page.getByRole('complementary', { name: 'Original text' }),
  ).toContainText('Budget: $100.')
  await page.getByRole('button', { name: 'Review again' }).click()
  await expect(page.getByText('Results saved', { exact: true })).toBeVisible()
  await page.reload()
  await expect(
    workspaceNav(page).getByRole('button', {
      name: 'Document reviews',
      exact: true,
    }),
  ).toHaveAttribute('aria-current', 'page')
  await expect(
    page.getByRole('heading', { name: 'Community workshop application' }),
  ).toBeVisible()
  await page.getByLabel('Run version').selectOption({ value: '0' })
  await page.getByRole('tab', { name: 'Original text', exact: true }).click()
  await expect(
    page.getByLabel('Document', { exact: true }).locator('option'),
  ).toHaveCount(1)
  await page.getByLabel('Run version').selectOption({ value: '1' })
  await expect(
    page.getByLabel('Document', { exact: true }).locator('option'),
  ).toHaveCount(2)
  await page.getByRole('tab', { name: 'Run details' }).click()
  await expect(page.getByText('Quotes matched to your documents')).toBeVisible()
  expect(state.executions).toBe(2)
  await expectFitsViewport(page)
})

for (const failure of ['network', 'rate-limit'] as const) {
  test(`refresh restarts polling after ${failure} without another execution`, async ({
    page,
  }) => {
    const state = await openReviews(page)
    await create(page)
    state.pollFailure = failure
    state.runningReads = 1
    await page.getByRole('button', { name: 'Run review', exact: true }).click()
    await expect(page.getByRole('alert')).toBeVisible()
    await page.getByRole('button', { name: 'Refresh reviews' }).click()
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(
      page.getByRole('heading', { name: 'More information needed' }),
    ).toBeVisible()
    expect(state.executions).toBe(1)
    expect(state.runningReads).toBe(0)
  })
}

test('inbox counts reflect loaded records and status filters', async ({
  page,
}, testInfo) => {
  const state = await openReviews(page)
  await expect(
    page.getByRole('heading', { name: 'No reviews yet' }),
  ).toBeVisible()
  await expect(page.locator('.review-overview dd')).toHaveText([
    '0',
    '0',
    '0',
    '0',
  ])
  await create(page)
  await page.getByRole('button', { name: 'Run review', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'More information needed' }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Back to reviews' }).click()
  await expect(page.locator('.overview-all dd')).toHaveText('1')
  await expect(page.locator('.overview-waiting_input dd')).toHaveText('1')
  await expect(page.locator('.overview-running dd')).toHaveText('0')
  await expect(page.locator('.overview-completed dd')).toHaveText('0')
  await page
    .getByLabel('Review status', { exact: true })
    .selectOption('completed')
  await expect(
    page.getByRole('heading', { name: 'No matching reviews' }),
  ).toBeVisible()
  await page
    .getByLabel('Review status', { exact: true })
    .selectOption('waiting_input')
  await expect(page.locator('.review-row')).toHaveCount(1)
  await expect(page.locator('.review-row')).toContainText(state.document!.title)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await expectFitsViewport(page)
  expect(
    await page.evaluate(
      () =>
        document
          .getAnimations()
          .filter((animation) => animation.playState === 'running').length,
    ),
  ).toBe(0)
  await page.screenshot({
    path: testInfo.outputPath('review-inbox.png'),
    fullPage: true,
  })
})

test('conflict preserves review and never silently resubmits', async ({
  page,
}) => {
  const state = await openReviews(page)
  await create(page)
  state.conflict = true
  await page.getByRole('button', { name: 'Run review', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('This review changed')
  expect(state.executions).toBe(0)
})

test('preview accepts a synthetic draft but never executes', async ({
  page,
}, testInfo) => {
  await openReviews(page, true)
  await page.getByRole('button', { name: 'New review', exact: true }).click()
  await page.getByRole('button', { name: 'Use sample text' }).click()
  await expect(
    page.getByRole('button', { name: 'Create shared review' }),
  ).toBeDisabled()
  await expect(page.getByLabel('Review title')).toHaveValue(
    'Community workshop application',
  )
  await screenshot(page, testInfo, 'review-draft.png')
  await expectFitsViewport(page)
})
