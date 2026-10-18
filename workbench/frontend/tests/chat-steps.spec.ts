import { expect, test } from '@playwright/test'
import { agent, openSteps, openWorkspace, send } from './helpers/chat-lab'
import { hoodSwitch } from './helpers/navigation'

test('How I got this lists the recorded steps in plain words', async ({
  page,
}, testInfo) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await openWorkspace(page)
  await send(page)
  const panel = page.locator('.answer-steps')
  await expect(panel).not.toHaveAttribute('open')
  await expect(panel.locator('summary')).toHaveText(
    /How I got this\s*Asked another agent/,
  )
  const steps = await openSteps(page)
  await expect(steps.locator('.answer-step-text')).toHaveText([
    /^Asked the Application review agent for its part of the answer/,
    /^Wrote the answer/,
  ])
  await expect(steps.locator('.answer-step-state')).toHaveText(['Confirmed'])
  await expect(panel).toContainText(
    'Confirmed means the Lab has a record that the step ran.',
  )
  await expect(page.locator('.review-note')).toBeInViewport({ ratio: 1 })
  await expect(page.locator('.review-note')).toContainText(
    'Check this answer before you use it.',
  )
  await expect(
    page.getByRole('button', { name: 'Continue in a new chat' }),
  ).toBeVisible()
  await expect(page.locator('.receipt-details')).not.toHaveAttribute('open')
  expect(
    await panel.evaluate(
      (element) =>
        element.getBoundingClientRect().right <= innerWidth &&
        document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  await panel.screenshot({ path: testInfo.outputPath('answer-steps.png') })
  await page.emulateMedia({ colorScheme: 'dark' })
  await expect(steps.getByText('Confirmed', { exact: true })).toBeVisible()
  await panel.screenshot({ path: testInfo.outputPath('answer-steps-dark.png') })
})

test('How I got this keeps tool names and timing under the hood', async ({
  page,
}) => {
  await openWorkspace(page)
  await send(page)
  const steps = await openSteps(page)
  // Tests run with Under the hood on.
  await expect(steps.locator('.answer-step').first()).toContainText(
    'inspect_application \u2192 application-review-agent',
  )
  await expect(steps.locator('.answer-step').last()).toContainText(/s total/)
  await hoodSwitch(page).uncheck()
  await expect(steps.getByText('inspect_application')).toBeHidden()
  await expect(steps.getByText(/s total/)).toBeHidden()
})

test('How I got this marks unconfirmed steps', async ({ page }) => {
  await openWorkspace(page, {
    receipts: [
      {
        tool: 'inspect_application',
        call_id: null,
        verified: false,
        agent: null,
        output: null,
      },
    ],
  })
  await send(page)
  const steps = await openSteps(page)
  await expect(steps.locator('.answer-step').first()).toHaveClass(/unverified/)
  await expect(steps.locator('.answer-step-text').first()).toHaveText(
    /^Checked the application/,
  )
  await expect(steps.locator('.answer-step-state')).toHaveText([
    'Not confirmed',
  ])
  await expect(steps.getByText('Confirmed', { exact: true })).toHaveCount(0)
})

test('self-targeted lookups on a created agent read as lookups, not a handoff', async ({
  page,
}) => {
  const created = {
    ...agent,
    id: 'created-service-planner',
    label: 'Service request planner',
    agent: 'service-request-planner-1a2b',
    tools: { lookup_demo_request: 'service-request-planner-1a2b' },
  }
  await openWorkspace(page, {
    config: { agents: [created], default_agent: created.id },
    receipts: [
      {
        tool: 'lookup_demo_request',
        call_id: 'call-1',
        verified: true,
        agent: created.agent,
        output: 'Synthetic request record.',
      },
    ],
  })
  await send(page)
  await expect(page.locator('.answer-steps summary')).toHaveText(
    /How I got this\s*Used 1 lookup/,
  )
  const steps = await openSteps(page)
  await expect(steps.locator('.answer-step-text').first()).toHaveText(
    /^Looked up the request/,
  )
  await expect(steps).not.toContainText('Asked')
})

test('answers without receipts say no steps were recorded', async ({
  page,
}) => {
  await openWorkspace(page, { receipts: [] })
  await send(page)
  await expect(page.locator('.assistant-message')).toContainText(
    'Section 1 is missing a budget.',
  )
  await expect(page.locator('.answer-steps summary')).toHaveText(
    /How I got this\s*No lookups or other agents recorded/,
  )
  const steps = await openSteps(page)
  await expect(steps.locator('.answer-step-text')).toHaveText([
    /^Wrote the answer/,
  ])
  await expect(page.locator('.receipt-details > summary')).toContainText(
    'Execution details',
  )
})
