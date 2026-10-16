import { expect, test } from '@playwright/test'
import { docsScreenshot, guidedReview } from './fixtures'
import { openWorkspace } from './helpers/chat-lab'
import { openLibraryTab } from './helpers/navigation'

test('shared privacy notice is visible before sending or saving', async ({
  page,
}, testInfo) => {
  await openWorkspace(page)
  const notice = page.locator('#chat-privacy')
  await expect(notice).toBeVisible()
  await expect(notice).toBeInViewport({ ratio: 1 })
  await expect(notice).toContainText(
    'never personal or confidential information',
  )
  await expect(notice).toContainText(
    'Saving shares completed messages with everyone in this Lab for 30 days after the last update.',
  )
  await expect(page.getByRole('textbox', { name: 'Message' })).toHaveAttribute(
    'aria-describedby',
    /chat-privacy/,
  )
  await expect(
    page.getByRole('button', { name: 'Save to shared history' }),
  ).toHaveAttribute('aria-describedby', 'chat-privacy')
  await page.screenshot({
    path: testInfo.outputPath('chat-privacy-mocked-apis.png'),
    fullPage: true,
    animations: 'disabled',
  })
})

test('preview chat does not promise shared persistence', async ({ page }) => {
  await openWorkspace(page, { preview: true })
  await expect(page.locator('#chat-privacy')).toHaveCount(0)
})

test('local preview offers Copy prompt instead of a Send that cannot work', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  const state = await openWorkspace(page, { preview: true })
  const box = page.getByRole('textbox', { name: 'Message' })
  const copy = page.getByRole('button', { name: 'Copy prompt' })
  await expect(page.getByRole('button', { name: 'Send message' })).toHaveCount(
    0,
  )
  await expect(page.locator('.composer-toolbar')).toContainText(
    'Local preview makes no model calls',
  )
  await expect(copy).toBeDisabled()
  await box.fill('Synthetic request')
  await expect(copy).toBeEnabled()
  await box.press('Enter')
  await copy.click()
  await expect
    .poll(() => page.evaluate(() => navigator.clipboard.readText()))
    .toContain('Synthetic request')
  await expect(page.locator('.user-message')).toHaveCount(0)
  await expect(page.getByRole('alert')).toHaveCount(0)
  expect(state.requests).toHaveLength(0)
})

test('storage-disabled chat does not promise shared persistence', async ({
  page,
}) => {
  await openWorkspace(page, { config: { history_enabled: false } })
  await expect(page.locator('#chat-privacy')).toBeVisible()
  await expect(page.locator('#chat-privacy')).not.toContainText('Saving shares')
})

test('chat starts with focused controls and preserves drafts when choosing an agent', async ({
  page,
}) => {
  const state = await openWorkspace(page)
  await expect(
    page.getByRole('heading', {
      name: 'Checklist and case helper',
      exact: true,
    }),
  ).toBeVisible()
  await expect(
    page.getByText('Foundry Agent Lab', { exact: true }),
  ).toHaveCount(1)
  await expect(page.locator('body')).not.toContainText(
    /A LITTLE CONTEXT|Evidence-grounded\. Human-reviewed\.|CURRENT CONVERSATION/,
  )
  await expect(
    page.locator('.conversation-heading, .composer-footnote'),
  ).toHaveCount(0)
  await expect(page.locator('#context-budget')).toHaveCount(0)
  await expect(page.getByText('Not saved', { exact: true })).toHaveCount(0)

  await page
    .getByRole('button', { name: 'Check against a checklist', exact: true })
    .click()
  const editor = page.getByRole('textbox', { name: 'Message', exact: true })
  await expect(editor).toHaveValue('Synthetic configured starter')
  await expect(editor).toBeFocused()
  await expect(page.getByText('Not saved', { exact: true })).toHaveCount(0)
  await expect(page.locator('#context-budget')).toHaveCount(0)

  await page
    .getByRole('banner')
    .getByTitle('Change agent', { exact: true })
    .click()
  const switcher = page.getByRole('dialog', { name: 'Choose an agent' })
  await expect(switcher).toBeVisible()
  await expect(
    switcher.getByRole('button', { name: /Checklist and case helper/ }),
  ).toHaveAttribute('aria-current', 'true')
  await page.keyboard.press('Escape')
  await expect(switcher).toHaveCount(0)
  await expect(editor).toHaveValue('Synthetic configured starter')
  await editor.fill('')
  await expect(page.locator('#context-budget')).toHaveCount(0)
  await expect(page.getByText('Not saved', { exact: true })).toHaveCount(0)
  expect(state.requests).toHaveLength(0)
})

test('default helper explains its job and offers example tasks without auto-sending', async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name === 'mobile')
  const state = await openWorkspace(page, {
    config: { agents: [guidedReview] },
  })
  await expect(page.locator('.agent-picker .agent-name')).toHaveText(
    'Checklist and case helper',
  )
  await expect(page.locator('.chat-welcome')).not.toContainText(
    'You are using an existing agent, not creating one',
  )
  await expect(page.locator('.chat-welcome .agent-guide')).toContainText(
    guidedReview.guidance!.input,
  )
  await expect(page.locator('.chat-welcome .agent-guide')).toContainText(
    guidedReview.guidance!.output,
  )
  await expect(page.locator('.prompt-options button small')).toHaveText([
    'Before this project goes for sign-off, check it against our checklist.',
    'Summarize these client notes for the team.',
    'Compare this vendor proposal with our requirements.',
    'What can you help me with?',
  ])
  await expect(page.locator('.prompt-options button strong')).toHaveText([
    'Check against a checklist',
    'Summarize case notes',
    'Compare a proposal (preview)',
    'Help me get started',
  ])
  await expect(page.locator('#chat-privacy')).toBeInViewport({ ratio: 1 })
  await expect(page.getByRole('region', { name: 'Ask the Lab' })).toHaveCount(0)
  await docsScreenshot(page, testInfo, 'demo-starters.png')
  await page.emulateMedia({ colorScheme: 'dark' })
  await docsScreenshot(page, testInfo, 'demo-starters-dark.png')
  await page.emulateMedia({ colorScheme: 'light' })
  const editor = page.getByRole('textbox', { name: 'Message', exact: true })
  for (const prompt of guidedReview.prompts) {
    await page.getByRole('button', { name: prompt.label, exact: true }).click()
    await expect(editor).toHaveValue(prompt.text)
    await expect(editor).toBeFocused()
    expect(state.requests).toHaveLength(0)
    // The cards stay, with the chosen one marked, so another can replace it
    // while the message box still holds the unedited example.
    await expect(page.locator('.prompt-options button')).toHaveCount(
      guidedReview.prompts.length,
    )
    await expect(
      page.getByRole('button', { name: prompt.label, exact: true }),
    ).toHaveAttribute('aria-pressed', 'true')
    await expect(page.locator('.welcome-hint')).toContainText(
      'Your example is in the message box below.',
    )
  }
  await openLibraryTab(page, /^Ready to chat/)
  await expect(page.locator('.catalog-agent')).toHaveCount(1)
  await expect(
    page.getByRole('heading', {
      name: 'Checklist and case helper',
      exact: true,
    }),
  ).toBeVisible()
  await page
    .getByRole('button', { name: 'Return to chat', exact: true })
    .click()
  const proposal = guidedReview.prompts[2]
  await page.getByRole('button', { name: proposal.label, exact: true }).click()
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(
    page.getByRole('button', { name: 'Save to shared history' }),
  ).toBeEnabled()
  expect(state.requests).toEqual([
    {
      agent_id: 'customer-review',
      input: proposal.text,
      history: [],
      thread: expect.stringMatching(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
      ),
    },
  ])
  await page.locator('.receipt-details > summary').click()
  await expect(
    page.getByText('Verified receipt', { exact: true }),
  ).toBeVisible()
  await expect(page.locator('.receipt')).toContainText('inspect_application')
  await expect(page.locator('.receipt')).toContainText(
    'application-review-agent',
  )
})

test('layout, text contrast and reduced motion', async ({ page }, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await openWorkspace(page)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.evaluate(() => document.fonts.ready)
  const geometry = await page.evaluate(() => ({
    overflow: document.documentElement.scrollWidth > innerWidth,
    editor: document
      .querySelector('textarea')!
      .getBoundingClientRect()
      .toJSON(),
    height: innerHeight,
    width: innerWidth,
    animations: document
      .getAnimations()
      .filter((animation) => animation.playState === 'running').length,
  }))
  expect(geometry.overflow).toBeFalsy()
  expect(geometry.editor.bottom).toBeLessThanOrEqual(geometry.height)
  expect(geometry.editor.right).toBeLessThanOrEqual(geometry.width)
  expect(geometry.animations).toBe(0)
  const contrast = await page
    .locator('.composer-toolbar > span')
    .evaluate((element) => {
      const channels = getComputedStyle(element)
        .color.match(/[\d.]+/g)!
        .slice(0, 3)
        .map(Number)
        .map((value) => {
          const normalized = value / 255
          return normalized <= 0.04045
            ? normalized / 12.92
            : ((normalized + 0.055) / 1.055) ** 2.4
        })
      return (
        1.05 /
        (channels[0] * 0.2126 +
          channels[1] * 0.7152 +
          channels[2] * 0.0722 +
          0.05)
      )
    })
  expect(contrast).toBeGreaterThanOrEqual(4.5)
  expect(errors).toEqual([])
  await page.screenshot({ path: testInfo.outputPath('workspace.png') })
})

test('composer grows within viewport bounds and shrinks again', async ({
  page,
}, testInfo) => {
  await openWorkspace(page)
  const editor = page.getByRole('textbox', { name: 'Message', exact: true })
  const initial = (await editor.boundingBox())!
  await editor.fill('Synthetic evidence line\n'.repeat(25))
  const grown = (await editor.boundingBox())!
  expect(grown.height).toBeGreaterThan(initial.height)
  expect(grown.height).toBeLessThanOrEqual(240)
  expect(grown.y + grown.height).toBeLessThan(page.viewportSize()!.height)
  await expect(
    page.getByRole('button', { name: 'Send message' }),
  ).toBeInViewport()
  await page.screenshot({ path: testInfo.outputPath('expanded-composer.png') })
  await editor.fill('Short draft')
  expect((await editor.boundingBox())!.height).toBeLessThan(grown.height)
})
