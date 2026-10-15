import { type Locator, type Page, expect, test } from '@playwright/test'
import { agent, openWorkspace, send } from './helpers/chat-lab'

test('while waiting, Chat says what the agent returns and reassures after a long wait', async ({
  page,
}) => {
  await page.clock.install()
  const state = await openWorkspace(page, { stalledReview: true })
  await page.getByRole('textbox', { name: 'Message' }).fill('Synthetic request')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => state.requests.length).toBe(1)
  const waiting = page.getByRole('status').filter({ hasText: 'Asking' })
  await expect(waiting).toContainText('Expect:')
  await expect(waiting).toContainText(agent.guidance!.output)
  await expect(waiting).not.toContainText('Still working')
  await page.clock.runFor(20001)
  await expect(waiting).toContainText('Still working')
  await expect(waiting).toContainText(
    'Some answers take 30 seconds to a minute, especially the first one in a new chat.',
  )
  await expect(waiting).toContainText(
    'Follow-up questions in the same chat usually take a few seconds.',
  )
  await expect(waiting).toContainText(agent.guidance!.output)
  await expect(
    waiting.locator('[aria-hidden="true"]').filter({ hasText: /^\d+s$/ }),
  ).toHaveCount(1)
})

test('the answer formatter loads on the first Send and formats the answer', async ({
  page,
}) => {
  const scripts: string[] = []
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname
    if (/\/assets\/MarkdownText-[\w-]+\.js$/.test(path)) scripts.push(path)
  })
  await openWorkspace(page, {
    answer:
      '**Budget missing.**\n\n| Item | Status |\n| --- | --- |\n| Budget | Missing |',
  })
  expect(scripts).toHaveLength(0)
  await send(page)
  const answer = page.locator('.message-markdown').first()
  await expect(answer.locator('strong')).toHaveText('Budget missing.')
  await expect(answer.locator('table tbody tr')).toHaveCount(1)
  expect(scripts).toHaveLength(1)
})

test('the answer stays readable if the formatter cannot load', async ({
  page,
}) => {
  await page.route('**/assets/MarkdownText-*.js', (route) => route.abort())
  await openWorkspace(page, { answer: 'Budget missing in Section 1.' })
  await send(page)
  await expect(page.locator('.message-markdown pre').first()).toHaveText(
    'Budget missing in Section 1.',
  )
})

test('a long answer opens at its start while a short one stays fully in view', async ({
  page,
}) => {
  const long = [
    '# Long sample answer',
    ...Array.from(
      { length: 60 },
      (_, index) => `Line ${index + 1} of the sample answer.`,
    ),
  ].join('\n\n')
  await openWorkspace(page, {
    answers: ['Section 1 is missing a budget.', long],
  })
  const answers = page.locator('.assistant-message')
  await send(page)
  await expect(answers).toHaveCount(1)
  await expect(answers.last()).toBeInViewport({ ratio: 1 })

  await send(page, 'Review a second synthetic request')
  await expect(answers).toHaveCount(2)
  const gap = () =>
    page.evaluate(() => {
      const top = (selector: string) => {
        const found = document.querySelectorAll(selector)
        return found[found.length - 1].getBoundingClientRect().top
      }
      return Math.round(top('.assistant-message') - top('.conversation-scroll'))
    })
  await expect.poll(gap).toBeGreaterThanOrEqual(0)
  await expect.poll(gap).toBeLessThanOrEqual(24)
  await expect(
    page.getByRole('heading', { name: 'Long sample answer' }),
  ).toBeInViewport()
  await expect(
    page.getByText('Line 60 of the sample answer.', { exact: true }),
  ).not.toBeInViewport()
})
test('stop waiting does not automatically retry', async ({ page }) => {
  const state = await openWorkspace(page, { stalledReview: true })
  await page.getByRole('textbox', { name: 'Message' }).fill('Synthetic request')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => state.requests.length).toBe(1)
  await expect(page.getByRole('textbox', { name: 'Message' })).toHaveValue('')
  await page.getByRole('button', { name: 'Stop waiting' }).click()
  await expect(page.getByRole('alert')).toContainText('Stopped waiting')
  await expect(page.getByRole('textbox', { name: 'Message' })).toHaveValue(
    'Synthetic request',
  )
  expect(state.requests).toHaveLength(1)
})

test('a busy model asks the visitor to wait instead of blaming the connection', async ({
  page,
}) => {
  const state = await openWorkspace(page, { busyReview: true })
  await page.getByRole('textbox', { name: 'Message' }).fill('Synthetic request')
  await page.getByRole('button', { name: 'Send message' }).click()
  const alert = page.getByRole('alert')
  await expect(alert).toContainText('The Lab is busy right now.')
  await expect(alert).toContainText('Reference: request-busy')
  await expect(alert).not.toContainText(/connectivity|managed-identity/i)
  await expect(page.getByRole('textbox', { name: 'Message' })).toHaveValue(
    'Synthetic request',
  )
  expect(state.requests).toHaveLength(1)
})

test('a busy reply counts down its Retry-After, then unlocks Retry', async ({
  page,
}) => {
  await page.clock.install()
  const state = await openWorkspace(page, { busyOnce: true })
  await page.getByRole('textbox', { name: 'Message' }).fill('Synthetic request')
  await page.getByRole('button', { name: 'Send message' }).click()
  const retry = page.getByRole('alert').getByRole('button', { name: 'Retry' })
  await expect(retry).toBeDisabled()
  await expect(retry).toContainText('in 12s')
  await page.clock.runFor(5000)
  await expect(retry).toContainText('in 7s')
  await expect(retry).toBeDisabled()
  await page.clock.runFor(7000)
  await expect(retry).toBeEnabled()
  await expect(retry).not.toContainText(/\d+s/)
  expect(state.requests).toHaveLength(1)
})

test('a blocked request shows its HTTP status and x-azure-ref, and Copy details copies them', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  const state = await openWorkspace(page, { blockedReview: true })
  await page.getByRole('textbox', { name: 'Message' }).fill('Synthetic request')
  await page.getByRole('button', { name: 'Send message' }).click()
  const alert = page.getByRole('alert')
  await expect(alert).toContainText('Request failed (HTTP 403).')
  await expect(alert).toContainText('Reference: azure-ref-123')
  await alert.getByRole('button', { name: 'Copy details' }).click()
  const copied = await page.evaluate(() => navigator.clipboard.readText())
  expect(copied).toContain('HTTP 403')
  expect(copied).toContain('Reference: azure-ref-123')
  expect(state.requests).toHaveLength(1)
})

test('Send clears the box, a failure restores it, and Retry resends it', async ({
  page,
}) => {
  await page.clock.install()
  const state = await openWorkspace(page, { busyOnce: true })
  const box = page.getByRole('textbox', { name: 'Message' })
  await box.fill('Synthetic request')
  await page.getByRole('button', { name: 'Send message' }).click()
  const alert = page.getByRole('alert')
  await expect(alert).toContainText('The Lab is busy right now')
  await expect(box).toHaveValue('Synthetic request')
  await expect(page.locator('.user-message')).toHaveCount(0)
  await expect(page.locator('.assistant-message')).toHaveCount(0)
  await page.clock.runFor(12001)
  await alert.getByRole('button', { name: 'Retry' }).click()
  await expect(page.locator('.assistant-message')).toHaveCount(1)
  await expect(page.locator('.user-message')).toHaveCount(1)
  await expect(box).toHaveValue('')
  await expect(alert).toHaveCount(0)
  expect(state.requests).toHaveLength(2)
  expect(state.requests[1].history).toEqual([])
})

test('non-JSON gateway errors say what happened without exposing parsing details', async ({
  page,
}) => {
  const state = await openWorkspace(page, { gatewayError: true })
  await page.getByRole('textbox', { name: 'Message' }).fill('Synthetic request')
  await page.getByRole('button', { name: 'Send message' }).click()
  const alert = page.getByRole('alert')
  await expect(alert).toContainText('could not get a reply from its service')
  await expect(alert).toContainText('try again')
  await expect(alert).not.toContainText(/JSON|token/i)
  await expect(page.getByRole('textbox', { name: 'Message' })).toHaveValue(
    'Synthetic request',
  )
  expect(state.requests).toHaveLength(1)
})

test('UTF-8 byte limit prevents an oversized request', async ({ page }) => {
  const state = await openWorkspace(page)
  await page
    .getByRole('textbox', { name: 'Message' })
    .fill('\u20ac'.repeat(22000))
  await expect(
    page.getByRole('button', { name: 'Send message' }),
  ).toBeDisabled()
  await expect(page.getByRole('alert')).toContainText(
    'Request byte limit exceeded',
  )
  expect(state.requests).toHaveLength(0)
})

test('review deadline is distinct from Stop and does not retry', async ({
  page,
}) => {
  await page.clock.install()
  const state = await openWorkspace(page, {
    stalledReview: true,
    config: { review_timeout_ms: 5000 },
  })
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Synthetic review')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => state.requests.length).toBe(1)
  await page.clock.runFor(5001)
  await expect(page.getByRole('alert')).toContainText('Request timed out')
  await expect(page.getByRole('button', { name: 'Send message' })).toBeEnabled()
  await page.getByRole('button', { name: 'Performance', exact: true }).click()
  await expect(
    page.getByRole('cell', { name: 'timed-out', exact: true }),
  ).toBeVisible()
  expect(state.requests).toHaveLength(1)
})

test('continuation previews context and leaves saved source unchanged', async ({
  page,
}, testInfo) => {
  const state = await openWorkspace(page, { config: { max_history_turns: 0 } })
  await send(page)
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect(page.getByText('Saved / shared', { exact: true })).toBeVisible()
  const source = JSON.stringify(state.document)
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Next synthetic question')
  await expect(page.getByRole('alert')).toContainText(
    'Conversation turn limit reached',
  )
  await page.getByRole('button', { name: 'Continue in new chat' }).click()
  const dialog = page.getByRole('dialog', { name: 'Continue in new chat' })
  await expect(dialog).toBeVisible()
  await expect(
    dialog.getByRole('textbox', { name: 'Carry-over draft' }),
  ).toContainText('Previous reply (unverified context)')
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue('Next synthetic question')
  await page.getByRole('button', { name: 'Continue in new chat' }).click()
  await dialog
    .getByRole('textbox', { name: 'Carry-over draft' })
    .fill('Reviewed carry-over context')
  await page.screenshot({ path: testInfo.outputPath('continuation.png') })
  await dialog
    .getByRole('button', { name: 'Start new chat', exact: true })
    .click()
  await expect(dialog).not.toBeVisible()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue('Reviewed carry-over context')
  await expect(page.getByRole('button', { name: 'Send message' })).toBeEnabled()
  expect(state.requests).toHaveLength(1)
  expect(JSON.stringify(state.document)).toBe(source)
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => state.requests.length).toBe(2)
  expect(state.requests[1].history).toEqual([])
  expect(state.requests[1].thread).not.toBe(state.requests[0].thread)
})

async function openContinuation(page: Page) {
  await openWorkspace(page)
  await send(page)
  const opener = page.getByRole('button', { name: 'Continue in new chat' })
  await opener.focus()
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog', { name: 'Continue in new chat' })
  await expect(dialog).toBeVisible()
  return { opener, dialog }
}

const closers: [string, (page: Page, dialog: Locator) => Promise<void>][] = [
  ['Escape', (page) => page.keyboard.press('Escape')],
  [
    'Cancel',
    (_, dialog) =>
      dialog.getByRole('button', { name: 'Cancel', exact: true }).click(),
  ],
  [
    'the close button',
    (_, dialog) =>
      dialog.getByRole('button', { name: 'Close continuation' }).click(),
  ],
]
for (const [name, close] of closers) {
  test(`closing the continuation with ${name} puts focus back on its button`, async ({
    page,
  }) => {
    const { opener, dialog } = await openContinuation(page)
    await close(page, dialog)
    await expect(dialog).toHaveCount(0)
    await expect(opener).toBeFocused()
  })
}

test('starting the new chat from the continuation puts focus in the message box', async ({
  page,
}) => {
  const { dialog } = await openContinuation(page)
  await dialog
    .getByRole('button', { name: 'Start new chat', exact: true })
    .click()
  await expect(dialog).toHaveCount(0)
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toBeFocused()
})
