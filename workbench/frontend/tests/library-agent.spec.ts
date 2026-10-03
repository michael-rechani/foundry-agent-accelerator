import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { screenshot } from './fixtures'
import { scorecards, support, templates } from './helpers/catalog'
import { foundryPortal } from './helpers/lab-config'
import {
  openAgent,
  openLibrary,
  readyRecord,
  runtimeHash,
} from './helpers/library-lab'
import { workspaceNav } from './helpers/navigation'

test('details state limits, human decisions and never claim a recorded answer', async ({
  page,
}) => {
  const state = await openLibrary(page)
  await openAgent(page, support.label)
  await expect(page.locator('.library-decision')).toContainText(
    support.human_decision,
  )
  const tabs = page.getByRole('tablist', { name: 'Agent details' })
  await expect(tabs.getByRole('tab')).toHaveText([
    'Overview',
    'Try it',
    'Test results',
    'Take it to Foundry',
  ])
  await expect(tabs.getByRole('tab', { name: 'Overview' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  const panel = page.getByRole('tabpanel')
  await expect(panel).toContainText(support.limits)
  await expect(panel).toContainText(support.expected_behavior)
  await expect(panel).toContainText(
    'Based on its acceptance tests, not a recorded answer.',
  )
  for (const item of support.prerequisites)
    await expect(panel).toContainText(item)

  await tabs.getByRole('tab', { name: 'Take it to Foundry' }).click()
  await expect(panel).toContainText(
    'There is no one-click cross-environment deployment.',
  )
  await expect(panel.locator('.library-command')).toContainText(
    `bundle.py export-created --record ${support.id}-record.json`,
  )
  await expect(
    panel.getByRole('button', { name: 'Create this agent to get the package' }),
  ).toBeEnabled()
  await expect(panel).toContainText(
    'Nothing is created until you confirm on the last step.',
  )

  await page.getByRole('button', { name: 'Back to all agents' }).click()
  await expect(page.locator('.library-card')).toHaveCount(templates.length)
  expect(state.chat).toHaveLength(0)
  expect(state.drafts).toBe(0)
  expect(state.creations).toBe(0)
})

test('creating from the library preselects the template without preparing or publishing', async ({
  page,
}) => {
  const state = await openLibrary(page)
  await openAgent(page, support.label)
  await page.getByRole('tab', { name: 'Try it' }).click()
  await page
    .getByRole('button', { name: 'Create this agent to test it' })
    .click()
  await expect(
    page.getByRole('heading', { name: 'Create an agent', exact: true }),
  ).toBeVisible()
  await expect(
    page.locator('.creation-template[aria-pressed="true"]'),
  ).toContainText(support.label)
  await expect(
    page.getByRole('textbox', { name: 'What should the agent help with?' }),
  ).toHaveValue(support.example_request)
  await expect(
    page.getByRole('combobox', { name: 'Prepared template' }),
  ).toHaveValue(support.id)
  expect(state.drafts).toBe(0)
  expect(state.creations).toBe(0)
})

test('a created agent opens in Chat as a draft and its request is logged and measured', async ({
  page,
  context,
}, testInfo) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  const state = await openLibrary(page, { ready: true })
  await expect(
    page.locator('.library-card').filter({ hasText: support.label }),
  ).toContainText('Made in this Lab')
  await openAgent(page, support.label)
  await page.getByRole('tab', { name: 'Try it' }).click()
  await expect(page.getByRole('tabpanel')).toContainText(
    'Nothing happens until you press Send',
  )
  await page.getByRole('button', { name: 'Open your created agent' }).click()
  const editor = page.getByRole('textbox', { name: 'Message', exact: true })
  await expect(editor).toHaveValue(support.sample_input)
  await expect(page.locator('.agent-picker')).toContainText(
    'Support handoff helper',
  )
  expect(state.chat).toHaveLength(0)

  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.getByText('ILLUSTRATIVE ANSWER')).toBeVisible()
  expect(state.chat).toHaveLength(1)
  expect(state.chat[0].agent_id).toBe(readyRecord(support).id)

  const log = workspaceNav(page).getByRole('button', { name: /^Request log/ })
  await expect(log).toContainText('1')
  await log.click()
  const row = page
    .getByRole('table', { name: 'Request log' })
    .locator('tbody tr')
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('Support handoff helper')
  await expect(row).toContainText('Completed')
  await row.getByRole('button', { name: /fictional-request-0001/ }).click()
  await expect(page.getByText('Reference copied.')).toBeVisible()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
    'fictional-request-0001',
  )
  await screenshot(page, testInfo, 'request-log.png')

  await workspaceNav(page)
    .getByRole('button', { name: 'Performance', exact: true })
    .click()
  await expect(page.locator('.metric-strip-4 > div')).toHaveCount(4)
  await expect(
    page.getByRole('table', { name: 'Recent requests' }),
  ).toContainText('Support handoff helper')
  await expect(page.locator('.table-note').last()).toContainText(
    'choose Test results',
  )
  await screenshot(page, testInfo, 'performance.png')
})

test('export downloads the saved ready record needed by export-created', async ({
  page,
}) => {
  await openLibrary(page, { ready: true })
  await openAgent(page, support.label)
  await page.getByRole('tab', { name: 'Take it to Foundry' }).click()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download saved record' }).click()
  const file = await download
  expect(file.suggestedFilename()).toBe(`${support.id}-record.json`)
  const saved = JSON.parse(await readFile(await file.path(), 'utf8'))
  expect(saved).toMatchObject({
    status: 'ready',
    template_id: support.id,
    runtime_hash: runtimeHash,
    model: 'demo-reasoning-model',
  })
  await expect(page.getByRole('status')).toContainText(
    'Saved record downloaded.',
  )
})

test('take it to Foundry downloads the definition and test requests without creating anything', async ({
  page,
}) => {
  const state = await openLibrary(page)
  const agent = templates.find((item) => item.id === 'casework-assistant')!
  await openAgent(page, agent.label)
  await page.getByRole('tab', { name: 'Take it to Foundry' }).click()
  const panel = page.getByRole('tabpanel')

  const definitionDownload = page.waitForEvent('download')
  await panel.getByRole('button', { name: 'Download agent definition' }).click()
  const definitionFile = await definitionDownload
  expect(definitionFile.suggestedFilename()).toBe(
    'casework-assistant.foundry-agent.json',
  )
  const definition = JSON.parse(
    await readFile(await definitionFile.path(), 'utf8'),
  )
  expect(definition.definition).toEqual({
    kind: 'prompt',
    model: '<your-model-deployment>',
    instructions: agent.instructions,
    tools: [],
  })
  expect(definition.metadata.library_agent).toBe(agent.id)
  await expect(page.getByRole('status')).toContainText(
    'Agent definition downloaded.',
  )

  const cases = scorecards.scorecards.find(
    (card: { template_id: string }) => card.template_id === agent.id,
  ).cases
  await expect(panel).toContainText(
    `${cases.length} requests for a Foundry evaluation`,
  )
  const casesDownload = page.waitForEvent('download')
  await panel.getByRole('button', { name: 'Download test requests' }).click()
  const casesFile = await casesDownload
  expect(casesFile.suggestedFilename()).toBe(
    'casework-assistant.foundry-test-cases.jsonl',
  )
  const rows = (await readFile(await casesFile.path(), 'utf8'))
    .trimEnd()
    .split('\n')
    .map((line) => JSON.parse(line))
  expect(rows).toHaveLength(cases.length)
  expect(rows[0]).toEqual({
    query: cases[0].input,
    case_id: cases[0].id,
    category: cases[0].category,
    expected_behavior: cases[0].goal,
  })
  await expect(page.getByRole('status')).toContainText(
    'Test requests downloaded.',
  )
  expect(state.creations).toBe(0)
  expect(state.drafts).toBe(0)
})

test('an agent without test results still offers its definition', async ({
  page,
}) => {
  await openLibrary(page, { withoutResultsFor: support.id })
  await openAgent(page, support.label)
  await page.getByRole('tab', { name: 'Take it to Foundry' }).click()
  const panel = page.getByRole('tabpanel')
  await expect(panel).toContainText('This agent has no test requests yet.')
  await expect(
    panel.getByRole('button', { name: 'Download test requests' }),
  ).toHaveCount(0)
  await expect(
    panel.getByRole('button', { name: 'Download agent definition' }),
  ).toBeEnabled()
})

test('test requests that fail to load can be retried', async ({ page }) => {
  const state = await openLibrary(page)
  state.failScorecards = true
  await openAgent(page, 'Case summary writer')
  await page.getByRole('tab', { name: 'Take it to Foundry' }).click()
  const panel = page.getByRole('tabpanel')
  await expect(panel).toContainText('The test requests did not load.')
  await expect(
    panel.getByRole('button', { name: 'Download agent definition' }),
  ).toBeEnabled()
  state.failScorecards = false
  await panel.getByRole('button', { name: 'Try again' }).click()
  await expect(
    panel.getByRole('button', { name: 'Download test requests' }),
  ).toBeEnabled()
})

test('a created agent links to Foundry only under the hood', async ({
  page,
}) => {
  await openLibrary(page, { ready: true, portal: true })
  await openAgent(page, support.label)
  await page.getByRole('tab', { name: 'Take it to Foundry' }).click()
  const link = page.getByRole('link', { name: /Open this agent in Foundry/ })
  await expect(link).toHaveAttribute(
    'href',
    `${foundryPortal}/build/agents/lab-demo-12345678123442349234123456789abc/build`,
  )
  await page.getByRole('switch', { name: /Under the hood/ }).uncheck()
  await expect(link).toBeHidden()
})
