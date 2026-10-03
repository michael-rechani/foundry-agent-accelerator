import { expect, test, type Locator, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import type { Review } from '../src/review-client'
import { themeStorageKey } from '../src/theme'
import type { Config } from '../src/workspace-config'
import { guidedReview, registry } from './fixtures'

// Keyboard use of the Agent library tabs, the review tabs and the agent
// switcher, checked in every Look. Only mocked local requests are used.
const looks = ['classic', 'aurora', 'console'] as const

const catalog = JSON.parse(
  await readFile(
    new URL('./agent-templates.fixture.json', import.meta.url),
    'utf8',
  ),
)
const scorecards = JSON.parse(
  await readFile(
    new URL('../../agent_scorecards.json', import.meta.url),
    'utf8',
  ),
)
const template = catalog.templates.find(
  (item: { id: string }) => item.id === 'customer-support-brief',
)
const caseHelper = registry.find((item) => item.id === 'case-review')!

const reviewId = 'review-12345678-1234-1234-1234-123456789abc'
const evidence = [
  { id: 'SRC-1', text: 'Twelve weekly workshops beginning October 1.' },
]
const review: Review = {
  id: reviewId,
  title: 'Community workshop application',
  agent_id: guidedReview.id,
  status: 'completed',
  updated_at: '2026-09-06T00:00:00Z',
  _etag: '1',
  criteria: ['A delivery timeline is stated'],
  evidence,
  runs: [
    {
      id: 'run-1',
      started_at: '2026-09-06T00:00:00Z',
      elapsed_ms: 1200,
      input: { criteria: ['A delivery timeline is stated'], evidence },
      events: [
        { name: 'review_started', at: '2026-09-06T00:00:00Z' },
        { name: 'completed', at: '2026-09-06T00:00:01Z' },
      ],
      result: {
        summary: 'Application evidence reviewed.',
        findings: [
          {
            criterion_id: 'CRIT-1',
            assessment: 'supported',
            explanation: 'A delivery timeline is stated.',
            citations: [{ source_id: 'SRC-1', quote: evidence[0].text }],
          },
        ],
        questions: [],
      },
    },
  ],
}

async function open(page: Page, look: (typeof looks)[number], hash = '') {
  const config: Config = {
    title: 'Foundry Agent Lab',
    mode: 'private',
    agents: [guidedReview, caseHelper],
    default_agent: guidedReview.id,
    max_characters: 60000,
    max_request_bytes: 65536,
    max_history_turns: 10,
    review_timeout_ms: 190000,
    history_timeout_ms: 45000,
    retention_days: 30,
    history_enabled: false,
    reviews_enabled: true,
  }
  await page.addInitScript(
    ([key, value]) => localStorage.setItem(key, value),
    [
      themeStorageKey,
      JSON.stringify({ mode: 'light', accent: 'foundry', look }),
    ],
  )
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const respond = (json: unknown, status = 200) =>
      route.fulfill({ json, status })
    if (path === '/api/config') return respond(config)
    if (path === '/api/agent-templates') return respond(catalog)
    if (path === '/api/agent-scorecards') return respond(scorecards)
    if (path === '/api/agents') return respond({ items: [], limit: 5 })
    if (path === '/api/review-runs')
      return respond({ items: [review], cursor: null })
    if (path === `/api/review-runs/${reviewId}`) return respond(review)
    return respond({ error: 'not_found' }, 404)
  })
  await page.goto('/' + hash)
  await expect(page.locator('html')).toHaveAttribute('data-look', look)
}

// Walks a tab list with the keyboard and checks the ARIA tabs pattern: roving
// tabindex, arrow keys that wrap, Home and End, and the panel naming the tab.
async function checkTabs(tabs: Locator, panel: Locator, names: string[]) {
  const tab = (name: string) => tabs.getByRole('tab', { name, exact: true })
  await expect(tabs.getByRole('tab')).toHaveText(names)
  const panelId = await panel.getAttribute('id')
  expect(panelId).toBeTruthy()

  async function expectSelected(name: string) {
    await expect(tab(name)).toBeFocused()
    for (const other of names) {
      const selected = other === name
      await expect(tab(other)).toHaveAttribute(
        'aria-selected',
        String(selected),
      )
      await expect(tab(other)).toHaveAttribute(
        'tabindex',
        selected ? '0' : '-1',
      )
      await expect(tab(other)).toHaveAttribute('aria-controls', panelId!)
    }
    await expect(panel).toHaveAttribute(
      'aria-labelledby',
      (await tab(name).getAttribute('id'))!,
    )
  }

  await tab(names[0]).focus()
  await expectSelected(names[0])
  for (const name of names.slice(1)) {
    await tabs.page().keyboard.press('ArrowRight')
    await expectSelected(name)
  }
  await tabs.page().keyboard.press('ArrowRight')
  await expectSelected(names[0])
  await tabs.page().keyboard.press('ArrowLeft')
  await expectSelected(names.at(-1)!)
  await tabs.page().keyboard.press('Home')
  await expectSelected(names[0])
  await tabs.page().keyboard.press('End')
  await expectSelected(names.at(-1)!)

  // Only the selected tab is a Tab stop, so Tab leaves the list.
  await tabs.page().keyboard.press('Tab')
  await expect(
    tabs.getByRole('tab').and(tabs.page().locator(':focus')),
  ).toHaveCount(0)
  await expect(tab(names.at(-1)!)).toHaveAttribute('aria-selected', 'true')
}

for (const look of looks) {
  test(`agent library tabs work from the keyboard in the ${look} look`, async ({
    page,
  }) => {
    await open(page, look)
    await page
      .locator('.library-card')
      .filter({ hasText: template.label })
      .click()
    await expect(
      page.getByRole('heading', { level: 1, name: template.label }),
    ).toBeVisible()
    await checkTabs(
      page.getByRole('tablist', { name: 'Agent details' }),
      page.getByRole('tabpanel'),
      ['Overview', 'Try it', 'Test results', 'Take it to Foundry'],
    )
  })

  test(`review tabs work from the keyboard in the ${look} look`, async ({
    page,
  }) => {
    await open(page, look, '#' + reviewId)
    await expect(
      page.getByRole('heading', { name: review.title }),
    ).toBeVisible()
    const tabs = page.getByRole('tablist', { name: 'Review detail' })
    await checkTabs(tabs, page.getByRole('tabpanel'), [
      'Results',
      'Original text',
      'Run details',
    ])
    // The run picker sits in the same bar but is not a tab.
    await expect(tabs.getByLabel('Run version')).toBeVisible()
  })

  test(`agent switcher traps focus and returns it in the ${look} look`, async ({
    page,
  }) => {
    await open(page, look, '#chat')
    const trigger = page.locator('.agent-picker')
    await expect(trigger).toHaveText(guidedReview.label)
    const dialog = page.getByRole('dialog', { name: 'Choose an agent' })
    const stops = dialog.locator('input:not(:disabled), button:not(:disabled)')
    const focusedStop = async () =>
      stops.evaluateAll((elements) =>
        elements.indexOf(document.activeElement as HTMLElement),
      )

    // Open with the keyboard; focus moves to the search box.
    await trigger.focus()
    await page.keyboard.press('Enter')
    await expect(dialog).toBeVisible()
    await expect(dialog).toHaveAttribute('aria-modal', 'true')
    await expect(trigger).toHaveAttribute('aria-expanded', 'true')
    await expect(dialog.getByRole('searchbox')).toBeFocused()
    const count = await stops.count()
    expect(count).toBeGreaterThanOrEqual(4)

    // Tab never leaves the dialog and wraps from the last stop to the first.
    for (let step = 1; step < count; step++) {
      await page.keyboard.press('Tab')
      expect(await focusedStop()).toBe(step)
    }
    await expect(
      dialog.getByRole('button', { name: /Browse the full library/ }),
    ).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(dialog.getByRole('searchbox')).toBeFocused()

    // Shift+Tab wraps backwards from the first stop to the last.
    await page.keyboard.press('Shift+Tab')
    expect(await focusedStop()).toBe(count - 1)
    await page.keyboard.press('Shift+Tab')
    expect(await focusedStop()).toBe(count - 2)

    // Escape closes the dialog and puts focus back on the trigger.
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(trigger).toBeFocused()
    await expect(trigger).toHaveAttribute('aria-expanded', 'false')

    // Choosing an agent also returns focus to the trigger.
    await page.keyboard.press('Enter')
    await expect(dialog).toBeVisible()
    await page.keyboard.press('Tab')
    await expect(
      dialog.getByRole('button', { name: new RegExp(guidedReview.label) }),
    ).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(
      dialog.getByRole('button', { name: new RegExp(caseHelper.label) }),
    ).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(dialog).toHaveCount(0)
    await expect(trigger).toHaveText(caseHelper.label)
    await expect(trigger).toBeFocused()

    // Escape still works after clicking an inert part of the dialog.
    await page.keyboard.press('Enter')
    await expect(dialog).toBeVisible()
    await dialog.locator('h2').first().click()
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(trigger).toBeFocused()
  })
}

test('agent switcher keeps focus inside when a search leaves few results', async ({
  page,
}) => {
  await open(page, 'classic', '#chat')
  const trigger = page.locator('.agent-picker')
  const dialog = page.getByRole('dialog', { name: 'Choose an agent' })
  await trigger.click()
  const search = dialog.getByRole('searchbox')
  await expect(search).toBeFocused()
  await search.fill(caseHelper.label)
  await expect(
    dialog.getByRole('button', { name: new RegExp(guidedReview.label) }),
  ).toHaveCount(0)
  const option = dialog.getByRole('button', {
    name: new RegExp(caseHelper.label),
  })
  const browse = dialog.getByRole('button', {
    name: /Browse the full library/,
  })
  await page.keyboard.press('Tab')
  await expect(option).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(browse).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(search).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(browse).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(trigger).toBeFocused()
})
