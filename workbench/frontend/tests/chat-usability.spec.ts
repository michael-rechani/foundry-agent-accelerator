import { expect, test } from '@playwright/test'
import { agent, openWorkspace, send } from './helpers/chat-lab'

const message = (page: import('@playwright/test').Page) =>
  page.getByRole('textbox', { name: 'Message' })

test('the message box stays editable while a reply is pending and keeps the new draft', async ({
  page,
}) => {
  const state = await openWorkspace(page, { holdReview: true })
  await message(page).fill('First question')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.getByRole('button', { name: 'Stop waiting' })).toBeVisible()

  const box = message(page)
  await expect(box).toBeEditable()
  await expect(box).toHaveAttribute('placeholder', /write your next message/i)
  await box.fill('My next question')
  await box.press('Enter')
  await expect(page.getByText('You can keep typing')).toBeVisible()
  expect(state.requests).toHaveLength(1)
  await expect(page.getByRole('button', { name: 'Send message' })).toHaveCount(
    0,
  )

  state.release()
  await expect(page.locator('.assistant-message')).toHaveCount(1)
  await expect(box).toHaveValue('My next question')
  await expect(page.getByRole('button', { name: 'Send message' })).toBeEnabled()
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => state.requests.length).toBe(2)
  state.release()
  await expect(page.locator('.assistant-message')).toHaveCount(2)
  await expect(box).toHaveValue('')
})

test('a failed send puts the message back in the box', async ({ page }) => {
  await openWorkspace(page, { gatewayError: true })
  await message(page).fill('Original question')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(message(page)).toHaveValue('Original question')
})

test('wide answer tables keep whole words and scroll sideways', async ({
  page,
}) => {
  const columns = [
    'Expense category',
    'Submitted amount',
    'Approved amount',
    'Receipt attached',
    'Policy reference',
    'Reviewer comment',
    'Follow-up required',
  ]
  const row = columns.map((name) => `${name.split(' ')[0]}-value`)
  await openWorkspace(page, {
    answer: [
      `| ${columns.join(' | ')} |`,
      `| ${columns.map(() => '---').join(' | ')} |`,
      `| ${row.join(' | ')} |`,
    ].join('\n'),
  })
  await send(page)
  const region = page.getByRole('region', { name: 'Table' })
  await expect(region).toBeVisible()
  await expect(region.locator('table')).toBeVisible()
  const cells = await region
    .locator('th, td')
    .evaluateAll((nodes) =>
      nodes.map((node) => getComputedStyle(node).overflowWrap),
    )
  expect(cells.every((wrap) => wrap === 'normal')).toBe(true)
  const words = await region
    .locator('th')
    .evaluateAll((nodes) =>
      nodes.every(
        (node) => (node as HTMLElement).scrollWidth <= node.clientWidth + 1,
      ),
    )
  expect(words).toBe(true)
})

test('a table wider than the reply scrolls instead of squeezing', async ({
  page,
}) => {
  const columns = Array.from({ length: 10 }, (_, index) => `Column${index}name`)
  await openWorkspace(page, {
    answer: [
      `| ${columns.join(' | ')} |`,
      `| ${columns.map(() => '---').join(' | ')} |`,
      `| ${columns.map(() => 'Longerwordvalue').join(' | ')} |`,
    ].join('\n'),
  })
  await send(page)
  const region = page.getByRole('region', { name: 'Table' })
  const scrolls = await region.evaluate(
    (node) => node.scrollWidth > node.clientWidth,
  )
  expect(scrolls).toBe(true)
  await region.focus()
  await expect(region).toBeFocused()
})

test('the Check this answer reminder skips the Help me get started reply', async ({
  page,
}) => {
  const help = 'What can you help me with?'
  await openWorkspace(page, {
    answers: ['I review applications.', 'Section 1 is missing a budget.'],
    config: {
      agents: [
        {
          ...agent,
          prompts: [
            { label: 'Help me get started', text: help },
            { label: 'Check against a checklist', text: 'Synthetic starter' },
          ],
        },
      ],
    },
  })
  await send(page, help)
  await expect(page.locator('.assistant-message')).toHaveCount(1)
  await expect(
    page.getByText('Check this answer before you use it.'),
  ).toHaveCount(0)
  await send(page, 'Review synthetic APP-1')
  await expect(page.locator('.assistant-message')).toHaveCount(2)
  await expect(
    page.getByText('Check this answer before you use it.'),
  ).toHaveCount(1)
})

test('only the latest answer carries the reminder and visible tools', async ({
  page,
}) => {
  await openWorkspace(page, { answers: ['First answer', 'Second answer'] })
  await send(page, 'First question')
  await send(page, 'Second question')
  const turns = page.locator('.turn')
  await expect(turns).toHaveCount(2)
  await expect(page.locator('.review-note')).toHaveCount(1)
  await expect(turns.nth(1).locator('.review-note')).toBeVisible()
  await expect(turns.nth(0).locator('.response-tools')).toHaveCSS(
    'opacity',
    '0',
  )
  await expect(turns.nth(1).locator('.response-tools')).toHaveCSS(
    'opacity',
    '1',
  )

  await turns.nth(0).hover()
  await expect(turns.nth(0).locator('.response-tools')).toHaveCSS(
    'opacity',
    '1',
  )
  await turns.nth(0).getByRole('button', { name: 'Copy response' }).focus()
  await expect(turns.nth(0).locator('.response-tools')).toHaveCSS(
    'opacity',
    '1',
  )
})

test('an agent that passes work to specialists says so while you wait', async ({
  page,
}) => {
  await openWorkspace(page, {
    stalledReview: true,
    config: {
      agents: [{ ...agent, tools: { review_case: 'case-review-agent' } }],
    },
  })
  await message(page).fill('Synthetic request')
  await page.getByRole('button', { name: 'Send message' }).click()
  const waiting = page.getByRole('status').filter({ hasText: 'Asking' })
  await expect(waiting).toContainText('passing your task to specialist agents')
  await expect(waiting).toContainText('30 to 60 seconds')
})

test('an agent that works alone does not claim to pass work on', async ({
  page,
}) => {
  await openWorkspace(page, {
    stalledReview: true,
    config: { agents: [{ ...agent, tools: {} }] },
  })
  await message(page).fill('Synthetic request')
  await page.getByRole('button', { name: 'Send message' }).click()
  const waiting = page.getByRole('status').filter({ hasText: 'Asking' })
  await expect(waiting).toBeVisible()
  await expect(waiting).not.toContainText('specialist agents')
})

test('the carry-over button says what it does', async ({ page }) => {
  await openWorkspace(page)
  await send(page)
  const button = page.getByRole('button', { name: 'Continue in a new chat' })
  await expect(button).toBeVisible()
  await expect(button).toHaveAttribute('title', /Nothing is sent/)
})
