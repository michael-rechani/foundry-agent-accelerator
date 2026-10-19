import { expect, test } from '@playwright/test'
import { docsScreenshot, guidedReview, registry, screenshot } from './fixtures'
import { expectFitsViewport } from './helpers/layout'
import { followLink, libraryNav, workspaceNav } from './helpers/navigation'
import { create, expectReviewOpen, openReviews } from './helpers/reviews-lab'

test('navigation is labelled and conversation actions stay in Chat', async ({
  page,
}, testInfo) => {
  await openReviews(page, true)
  await expect(page.getByText('Local preview', { exact: true })).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'Review storage unavailable' }),
  ).toBeVisible()
  await expect(page.locator('.review-scope')).toContainText(
    'Check the text you paste against your own checklist',
  )
  await expect(page.locator('.review-intro')).toContainText(
    'Your Chat messages are not copied here, and review results are not sent back to Chat',
  )
  await expect(page.locator('.review-steps li')).toHaveText([
    'Add a checklist and document text',
    'Run a review',
    'Read results beside the original text',
    'Add missing information and review again',
  ])
  await expect(
    page.getByRole('complementary', { name: 'Lab data boundary' }),
  ).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: 'Save to shared history' }),
  ).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: 'Export conversation' }),
  ).toHaveCount(0)
  await screenshot(page, testInfo, 'reviews-navigation.png')
  const navigation = workspaceNav(page)
  for (const label of [
    'Chat',
    'Document reviews',
    'Shared history',
    'All agents',
    'Performance',
  ]) {
    await expect(
      navigation.locator('span').filter({ hasText: new RegExp(`^${label}$`) }),
    ).toBeVisible()
  }
  for (const label of ['Chat', 'All agents', 'Performance']) {
    await navigation.getByRole('button', { name: label, exact: true }).click()
    await expect(page.getByText('Local preview', { exact: true })).toBeVisible()
    await expect(
      page.getByRole('button', { name: 'Export conversation' }),
    ).toHaveCount(label === 'Chat' ? 1 : 0)
    await page.screenshot({
      path: testInfo.outputPath(
        `${label.toLowerCase().replaceAll(' ', '-')}.png`,
      ),
    })
  }
  await expectFitsViewport(page)
})

test('review guide explains findings, storage and human decision boundaries', async ({
  page,
}) => {
  const state = await openReviews(page)
  const guide = page.locator('.review-guide')
  await guide.locator('summary').click()
  await expect(guide.locator('dt')).toHaveText(['Supported', 'Gap', 'Conflict'])
  await expect(guide).toContainText('does not prove the text is true')
  await expect(guide).toContainText('does not mean the application has failed')
  await expect(guide).toContainText('Statements disagree')
  await expect(guide).toContainText('not whether it is true')
  await expect(guide).toContainText(
    'a copy of its input, results, follow-up questions and records of tool calls',
  )
  await expect(guide).toContainText(
    'Anyone who can open this Lab can read saved reviews and add requested information',
  )
  await expect(guide).toContainText('Records are not private to you')
  await expect(guide).toContainText('30 days after their last update')
  await expect(guide).toContainText(
    'cannot delete a review or edit its saved checklist',
  )
  await expect(guide).toContainText('not a continuation of Chat')
  await expect(guide).toContainText(
    'Requirements and proposal review is in preview',
  )
  expect(state.executions).toBe(0)
  expect(state.creations).toHaveLength(0)
})

test('document reviews use the Lab default and do not transfer Chat drafts', async ({
  page,
}, testInfo) => {
  const caseAgent = registry.find((item) => item.id === 'case-review')!
  const state = await openReviews(page, false, [guidedReview, caseAgent])
  const navigation = workspaceNav(page)
  await navigation.getByRole('button', { name: 'All agents' }).click()
  await libraryNav(page)
    .getByRole('button', { name: /^Ready to chat/ })
    .click()
  await page
    .locator('.catalog-agent')
    .filter({
      has: page.getByRole('heading', { name: caseAgent.label, exact: true }),
    })
    .getByRole('button', { name: 'Chat with this agent' })
    .click()
  const editor = page.getByRole('textbox', { name: 'Message', exact: true })
  await editor.fill('Fictional case notes only for Chat, not review evidence')
  await page.evaluate(() => {
    window.location.hash = ''
    window.location.hash = '#reviews'
  })
  await page.getByRole('button', { name: 'New review', exact: true }).click()
  await expect(page.getByLabel('Review title')).toHaveValue('')
  await expect(page.getByLabel('Checklist, one item per line')).toHaveValue('')
  await expect(page.getByLabel('Document 1', { exact: true })).toHaveValue('')
  await expect(page.locator('.review-form-bar')).toContainText(
    'Agent doing this check: Checklist and case helper',
  )
  await expect(page.locator('.review-form-bar')).toContainText(
    "Uses the Lab's default agent, not your Chat selection",
  )
  await page.getByRole('button', { name: 'Use sample text' }).click()
  expect(state.creations).toHaveLength(0)
  await expect(page.locator('#review-privacy')).toBeVisible()
  await expect(page.locator('#review-privacy')).toContainText(
    'never personal or confidential information',
  )
  await expect(page.locator('#review-privacy')).toContainText(
    'Reviews expire 30 days after the last update; backup retention is separate.',
  )
  await expect(
    page.getByRole('button', { name: 'Create shared review' }),
  ).toHaveAttribute('aria-describedby', 'review-privacy')
  await page
    .getByRole('button', { name: 'Create shared review' })
    .scrollIntoViewIfNeeded()
  await expect(page.locator('#review-privacy')).toBeInViewport({ ratio: 0.99 })
  await expect(
    page.getByRole('button', { name: 'Create shared review' }),
  ).toBeInViewport({ ratio: 1 })
  await docsScreenshot(page, testInfo, 'review-privacy.png')
  await page.emulateMedia({ colorScheme: 'dark' })
  await docsScreenshot(page, testInfo, 'review-privacy-dark.png')
  await page.emulateMedia({ colorScheme: 'light' })
  await page.getByRole('button', { name: 'Create shared review' }).click()
  await expect(
    page.getByRole('button', { name: 'Run review', exact: true }),
  ).toBeVisible()
  expect(state.creations).toHaveLength(1)
  expect(state.creations[0].agent_id).toBe('customer-review')
  expect(Object.keys(state.creations[0]).sort()).toEqual([
    'agent_id',
    'criteria',
    'evidence',
    'title',
  ])
  expect(JSON.stringify(state.creations[0])).not.toContain('only for Chat')
  expect(state.executions).toBe(0)
  expect(state.chatRequests).toBe(0)
  await navigation.getByRole('button', { name: 'Chat', exact: true }).click()
  await expect(page.locator('.agent-picker .agent-name')).toHaveText(
    caseAgent.label,
  )
  await expect(editor).toHaveValue(
    'Fictional case notes only for Chat, not review evidence',
  )
})

test('invalid review links fall back to the start page without opening a review', async ({
  page,
}) => {
  await openReviews(page)
  await page.goto('/#review-not-a-valid-id')
  await page.reload()
  await expect(
    workspaceNav(page).getByRole('button', { name: 'Find an agent' }),
  ).toHaveAttribute('aria-current', 'page')
  await expect(
    page.getByRole('heading', { level: 1, name: 'Welcome to the Lab' }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'Document reviews', exact: true }),
  ).toHaveCount(0)
})

test('a review link followed after the Lab has loaded opens the review', async ({
  page,
}) => {
  const state = await openReviews(page)
  await create(page)
  const link = '#' + state.document!.id
  const navigation = workspaceNav(page)

  await page.getByRole('button', { name: 'Back to reviews' }).click()
  await expect(
    page.getByRole('heading', { name: 'Document reviews', exact: true }),
  ).toBeVisible()
  await followLink(page, link)
  await expectReviewOpen(page)

  await page.getByRole('button', { name: 'Back to reviews' }).click()
  await navigation.getByRole('button', { name: 'Chat', exact: true }).click()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toBeVisible()
  await followLink(page, link)
  await expect(
    navigation.getByRole('button', {
      name: 'Document reviews',
      exact: true,
    }),
  ).toHaveAttribute('aria-current', 'page')
  await expectReviewOpen(page)
})

test('back and forward move between a review link and Chat', async ({
  page,
}) => {
  const state = await openReviews(page)
  await create(page)
  const navigation = workspaceNav(page)
  const chat = navigation.getByRole('button', { name: 'Chat', exact: true })
  const reviews = navigation.getByRole('button', {
    name: 'Document reviews',
    exact: true,
  })
  await page.goto('/#chat')
  await expect(chat).toHaveAttribute('aria-current', 'page')

  await page.goBack()
  await expect(reviews).toHaveAttribute('aria-current', 'page')
  await expectReviewOpen(page)
  expect(await page.evaluate(() => window.location.hash)).toBe(
    '#' + state.document!.id,
  )

  await page.goForward()
  await expect(chat).toHaveAttribute('aria-current', 'page')
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toBeVisible()

  await page.goBack()
  await expect(reviews).toHaveAttribute('aria-current', 'page')
  await expectReviewOpen(page)
})

test('following a review link asks before discarding a review that is being written', async ({
  page,
}) => {
  const state = await openReviews(page)
  await create(page)
  const link = '#' + state.document!.id
  await page.getByRole('button', { name: 'Back to reviews' }).click()
  await page.getByRole('button', { name: 'New review', exact: true }).click()
  await page.getByLabel('Review title').fill('Half-written fictional review')

  const asked: string[] = []
  page.once('dialog', (dialog) => {
    asked.push(dialog.message())
    void dialog.dismiss()
  })
  await followLink(page, link)
  await expect
    .poll(() => asked)
    .toEqual(['Discard unsaved review information?'])
  await expect(page.getByLabel('Review title')).toHaveValue(
    'Half-written fictional review',
  )
  await expect
    .poll(() => page.evaluate(() => window.location.hash))
    .toBe('#reviews')

  page.once('dialog', (dialog) => void dialog.accept())
  await followLink(page, link)
  await expectReviewOpen(page)
  await expect(page.getByLabel('Review title')).toHaveCount(0)
})

test('a review link followed from another page asks before discarding a review that is being written', async ({
  page,
}) => {
  const state = await openReviews(page)
  await create(page)
  const link = '#' + state.document!.id
  const navigation = workspaceNav(page)
  const chat = navigation.getByRole('button', { name: 'Chat', exact: true })
  await page.getByRole('button', { name: 'Back to reviews' }).click()
  await page.getByRole('button', { name: 'New review', exact: true }).click()
  await page.getByLabel('Review title').fill('Half-written fictional review')
  await chat.click()
  await expect(chat).toHaveAttribute('aria-current', 'page')

  const asked: string[] = []
  page.once('dialog', (dialog) => {
    asked.push(dialog.message())
    void dialog.dismiss()
  })
  await followLink(page, link)
  await expect
    .poll(() => asked)
    .toEqual(['Discard unsaved review information?'])
  await expect(page.getByLabel('Review title')).toHaveValue(
    'Half-written fictional review',
  )
  await expect
    .poll(() => page.evaluate(() => window.location.hash))
    .toBe('#reviews')

  await chat.click()
  page.once('dialog', (dialog) => void dialog.accept())
  await followLink(page, link)
  await expectReviewOpen(page)
  await expect(page.getByLabel('Review title')).toHaveCount(0)
})
