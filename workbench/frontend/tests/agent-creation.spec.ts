import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { screenshot } from './fixtures'
import {
  authorize,
  categories,
  navigate,
  openCreation,
  operatorKey,
  prepare,
  sample,
  templates,
} from './helpers/creation-lab'
import { expectFitsViewport } from './helpers/layout'
import { workspaceNav } from './helpers/navigation'

test('creation is the entry point with nine honest jobs in two groups and usable navigation', async ({
  page,
}, testInfo) => {
  const state = await openCreation(page)
  await expect(
    page.getByRole('heading', { name: 'Create an agent', exact: true }),
  ).toBeVisible()
  await expect(page.locator('.creation-template strong')).toHaveText(
    templates.map((item) => item.label),
  )
  await expect(page.locator('.creation-template-group h2')).toHaveText(
    categories,
  )
  await expect(
    page
      .getByRole('region', { name: 'Healthcare and public sector' })
      .locator('.creation-template small'),
  ).toHaveText(Array(4).fill('Sample read-only lookups'))
  await expect(
    page
      .getByRole('combobox', { name: 'Prepared template', exact: true })
      .locator('optgroup'),
  ).toHaveCount(2)
  await expect(page.locator('.creation-heading')).toContainText(
    'Start from a prepared template',
  )
  await expect(page.locator('.creation-heading')).not.toContainText(
    'healthcare-administration',
  )
  await expect(page.locator('.creation-steps li')).toHaveText([
    'Describe the job',
    'Review name, instructions and tools',
    'Create in Foundry and try it',
  ])
  await expect(
    page.getByRole('button', { name: 'Prepare setup', exact: true }),
  ).toBeDisabled()
  for (const label of [
    'Create agent',
    'All agents',
    'Chat',
    'Shared history',
    'Performance',
  ]) {
    await expect(
      workspaceNav(page).getByRole('button', { name: label, exact: true }),
    ).toBeVisible()
  }
  await expect(
    workspaceNav(page).getByRole('button', { name: 'Document reviews' }),
  ).toHaveCount(0)
  await expectFitsViewport(page)
  expect(state.posts).toHaveLength(0)
  expect(state.chat).toHaveLength(0)
  await screenshot(page, testInfo, 'creation-start.png')
})

test('template selection preserves custom input and brings the next step into view', async ({
  page,
}) => {
  await openCreation(page)
  const goal = page.getByLabel('What should the agent help with?')
  await goal.fill(
    'Explain the differences between my fictional policy notices.',
  )
  await page.locator('.creation-template').first().click()
  await expect(goal).toHaveValue(
    'Explain the differences between my fictional policy notices.',
  )
  await expect(goal).toBeFocused()
  await expect(goal).toBeInViewport()
  await page.getByRole('button', { name: 'Prepare setup', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Review your agent setup' }),
  ).toBeInViewport()
})

test('the step indicator, search and cost notice guide the create flow', async ({
  page,
}) => {
  await openCreation(page)
  const steps = page.locator('.creation-steps li')
  await expect(steps.nth(0)).toHaveAttribute('aria-current', 'step')
  await expect(steps.nth(1)).not.toHaveAttribute('aria-current', 'step')

  const cards = page.locator('.creation-template')
  const total = await cards.count()
  const search = page.getByRole('searchbox', { name: 'Search templates' })
  await search.fill('zzzz-no-such-template')
  await expect(cards).toHaveCount(0)
  await expect(page.getByRole('status')).toContainText('No templates match')
  await search.fill('')
  await expect(cards).toHaveCount(total)
  const first = (await cards.first().locator('strong').textContent()) ?? ''
  await search.fill(first.toLowerCase())
  expect(await cards.count()).toBeGreaterThan(0)
  expect(await cards.count()).toBeLessThanOrEqual(total)

  await cards.first().click()
  await expect(page.locator('.creation-picked')).toContainText(
    `Selected: ${first}`,
  )
  await page
    .getByLabel('What should the agent help with?')
    .fill('Explain the differences between my fictional policy notices.')
  await page.getByRole('button', { name: 'Prepare setup', exact: true }).click()
  await expect(steps.nth(1)).toHaveAttribute('aria-current', 'step')
  await expect(steps.nth(0)).toHaveAttribute('data-done', 'true')
  const costs = page.locator('.creation-costs')
  await expect(costs).toContainText('Before you create it')
  await expect(costs).toContainText(/Publishing takes up to \d+ minutes?/)
  await expect(costs).toContainText('keeps costing money until someone deletes')
})

test('ambiguous descriptions require a template and preparation creates no agent', async ({
  page,
}) => {
  const state = await openCreation(page)
  await page
    .getByLabel('What should the agent help with?')
    .fill('Help our fictional team with its work')
  await page.getByRole('button', { name: 'Prepare setup', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText(
    'Choose the closest prepared template',
  )
  await page
    .getByRole('combobox', { name: 'Prepared template', exact: true })
    .selectOption('casework-assistant')
  await page.getByRole('button', { name: 'Prepare setup', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Review your agent setup' }),
  ).toBeVisible()
  await expect(page.getByLabel('Agent name', { exact: true })).toHaveValue(
    'Case summary writer',
  )
  await expect(page.getByLabel('Task instructions')).toHaveValue(
    /Help our fictional team/,
  )
  await expect(
    page.getByRole('region', { name: 'Review agent setup' }),
  ).toContainText('No agent has been created yet')
  expect(state.drafts).toHaveLength(2)
  expect(state.posts).toHaveLength(0)
  expect(state.chat).toHaveLength(0)
})

test('publishes reviewed setup, uses its real ID in chat, saves and restores history without leaking keys', async ({
  page,
}, testInfo) => {
  const state = await openCreation(page)
  await prepare(page)
  await expect(page.locator('.creation-explanation')).toContainText(
    'demo-reasoning-model, chosen for Reasoning.',
  )
  await page
    .getByLabel('Agent name', { exact: true })
    .fill('Policy notice helper')
  await page.getByText(/^Task instructions: [\d,]+ characters/).click()
  await page
    .getByLabel('Task instructions')
    .fill(
      'Explain fictional policy notices. Cite labels and ask for the missing implementation date.',
    )
  await expect(
    page.getByRole('button', { name: 'Create in Foundry', exact: true }),
  ).toBeDisabled()
  await authorize(page)
  await page
    .getByRole('region', { name: 'Review agent setup' })
    .scrollIntoViewIfNeeded()
  await screenshot(page, testInfo, 'creation-setup.png')
  await page
    .getByRole('button', { name: 'Create in Foundry', exact: true })
    .click()
  await expect(page.locator('.creation-status')).toHaveText('Ready to try')
  await expect(page.getByLabel('Operator key', { exact: true })).toHaveValue('')
  expect(state.posts).toHaveLength(1)
  expect(state.posts[0].name).toBe('Policy notice helper')
  expect(state.posts[0].instructions).toContain('missing implementation date')
  await expect(page.locator('.creation-runtime')).toContainText(
    'demo-reasoning-model, chosen for Reasoning',
  )
  await page
    .getByRole('heading', { name: 'Policy notice helper', exact: true })
    .scrollIntoViewIfNeeded()
  await screenshot(page, testInfo, 'creation-ready.png')
  await page.getByRole('button', { name: 'Try in Chat', exact: true }).click()
  await expect(page.locator('.agent-picker')).toContainText(
    'Policy notice helper',
  )
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue('')
  expect(state.chat).toHaveLength(0)
  await page
    .getByRole('button', { name: 'Try the sample', exact: true })
    .click()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toHaveValue(sample)
  expect(state.chat).toHaveLength(0)
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
  await expect(
    page.getByRole('button', { name: 'Save to shared history' }),
  ).toBeEnabled()
  expect(state.chat).toEqual([
    {
      agent_id: state.record!.id,
      input: sample,
      history: [],
      thread: expect.stringMatching(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
      ),
    },
  ])
  await screenshot(page, testInfo, 'creation-chat.png')
  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export conversation' }).click()
  const download = await downloadEvent
  const exported = await readFile((await download.path())!, 'utf8')
  expect(exported).not.toContain(operatorKey)
  expect(exported).not.toContain(state.posts[0].instructions)
  expect(
    await page.evaluate(() =>
      JSON.stringify({ ...localStorage, ...sessionStorage }),
    ),
  ).not.toContain(operatorKey)
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect.poll(() => state.savedChat?.agent_id).toBe(state.record!.id)
  state.missingFromList = true
  await page.reload()
  await navigate(page, 'Shared history')
  await page
    .getByRole('button', { name: new RegExp('^' + sample.slice(0, 12)) })
    .click()
  await expect(page.locator('.agent-picker')).toContainText(
    'Policy notice helper',
  )
  await expect(page.getByText(/ILLUSTRATIVE ANSWER:/)).toBeVisible()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toBeEnabled()
  expect(state.posts).toHaveLength(1)
})

test('local preview prepares all nine templates but cannot publish or load saved agents', async ({
  page,
}, testInfo) => {
  const state = await openCreation(page, { preview: true })
  for (const template of templates) {
    await prepare(page, template.label)
    await expect(
      page.getByRole('button', { name: 'Create in Foundry', exact: true }),
    ).toBeDisabled()
    await expect(
      page.getByLabel('Operator key', { exact: true }),
    ).toBeDisabled()
    await expect(page.getByText('Local preview', { exact: true })).toBeVisible()
    await expect(page.locator('.creation-explanation')).toContainText(
      `Set by the Lab operator, chosen for ${template.model_profile.label}.`,
    )
    if (template.tools.length) {
      await expect(page.locator('.creation-tool-list li')).toHaveCount(2)
      await expect(page.locator('.creation-tool-list')).toContainText(
        '(sample data)',
      )
      if (template.id === 'medical-bill-reviewer')
        await screenshot(page, testInfo, 'creation-preview-tools.png')
    } else
      await expect(
        page.getByText('No tools or external integrations.', { exact: true }),
      ).toBeVisible()
    await page.getByRole('button', { name: 'Change task or template' }).click()
  }
  await navigate(page, 'Created agents')
  await expect(page.locator('.creation-workspace')).toContainText(
    'Created-agent storage is not connected',
  )
  expect(state.lists).toBe(0)
  expect(state.posts).toHaveLength(0)
  expect(state.chat).toHaveLength(0)
})

test('incorrect operator key preserves editable setup and does not claim success', async ({
  page,
}) => {
  const state = await openCreation(page)
  await prepare(page)
  await authorize(page, 'incorrect-fictional-key-12345678901234567890')
  await page
    .getByRole('button', { name: 'Create in Foundry', exact: true })
    .click()
  await expect(page.getByRole('alert')).toContainText(
    'That operator key was not accepted, so nothing was created or changed.',
  )
  await expect(page.getByRole('alert')).toContainText(
    'ask the Lab operator for the key',
  )
  await expect(page.getByLabel('Agent name', { exact: true })).toBeEnabled()
  await expect(page.getByLabel('Task instructions')).toBeEnabled()
  expect(state.record).toBeNull()
  await page.getByLabel('Operator key', { exact: true }).fill(operatorKey)
  await page
    .getByRole('button', { name: 'Create in Foundry', exact: true })
    .click()
  await expect(page.locator('.creation-status')).toHaveText('Ready to try')
  expect(state.posts).toHaveLength(2)
})

test('the operator key box says in plain words what the key is and who to ask', async ({
  page,
}) => {
  await openCreation(page)
  await prepare(page)
  const box = page.locator('.creation-key')
  await expect(box).toContainText(
    'A shared password for whoever runs this Lab.',
  )
  await expect(box).toContainText('create or delete a real agent in Foundry')
  await expect(box).toContainText('costs money')
  await expect(box).toContainText('Ask the Lab operator for it.')
  await expect(box).not.toContainText(/vault|secret/i)
  await expect(
    page.getByLabel('Operator key', { exact: true }),
  ).toHaveAttribute('type', 'password')
  await authorize(page, 'too-short')
  await page
    .getByRole('button', { name: 'Create in Foundry', exact: true })
    .click()
  await expect(page.getByRole('alert')).toContainText(
    'Ask the Lab operator if you do not have it.',
  )
})

test('a refused create request explains itself even when the setup is taller than the window', async ({
  page,
}) => {
  await page.setViewportSize({ width: 709, height: 560 })
  const state = await openCreation(page)
  await prepare(page)
  const workspace = page.locator('main.creation-workspace')
  expect(
    await workspace.evaluate((main) => main.scrollHeight > main.clientHeight),
  ).toBe(true)
  await authorize(page, 'too-short')
  const create = page.getByRole('button', {
    name: 'Create in Foundry',
    exact: true,
  })
  await create.scrollIntoViewIfNeeded()
  await create.click()
  const alert = page.getByRole('alert')
  await expect(alert).toContainText('at least 32 characters')
  await expect(alert).toBeInViewport()
  await expect(page.getByLabel('Operator key', { exact: true })).toBeFocused()
  expect(state.posts).toHaveLength(0)
})

for (const rejection of [400, 413]) {
  test(`rejected setup (${rejection}) stays editable rather than locking an unaccepted operation`, async ({
    page,
  }) => {
    const state = await openCreation(page)
    state.rejectSetup = rejection
    await prepare(page)
    await authorize(page)
    await page
      .getByRole('button', { name: 'Create in Foundry', exact: true })
      .click()
    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page.getByLabel('Agent name', { exact: true })).toHaveValue(
      'Document explainer',
    )
    await expect(page.getByLabel('Task instructions')).toBeEnabled()
    await expect(
      page.getByRole('button', { name: 'Retry same creation request' }),
    ).toHaveCount(0)
    expect(state.record).toBeNull()
  })
}
