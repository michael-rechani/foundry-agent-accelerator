import { expect, test } from '@playwright/test'
import { registry, screenshot } from './fixtures'
import { agent, openWorkspace, send } from './helpers/chat-lab'
import { expectFitsViewport, useNarrowLayout } from './helpers/layout'
import { hoodSwitch, openLibraryTab, workspaceNav } from './helpers/navigation'

test('catalog uses customer names while retaining runtime targets and scenario status', async ({
  page,
}) => {
  const state = await openWorkspace(page, { config: { agents: registry } })
  expect(
    registry.map(({ id, agent, tools }) => ({ id, agent, tools })),
  ).toEqual([
    {
      id: 'customer-review',
      agent: 'customer-review-coordinator',
      tools: {
        inspect_application: 'application-review-agent',
        inspect_case: 'case-review-agent',
      },
    },
    {
      id: 'review-coordinator',
      agent: 'review-coordinator-agent',
      tools: {
        review_application: 'application-review-agent',
        review_case: 'case-review-agent',
      },
    },
    { id: 'application-review', agent: 'application-review-agent', tools: {} },
    { id: 'case-review', agent: 'case-review-agent', tools: {} },
  ])
  await openLibraryTab(page, /^Ready to chat/)
  await expect(page.locator('.catalog-agent h2')).toHaveText([
    'Checklist and case helper',
    'Checklist and case helper (base setup)',
    'Checklist reviewer',
    'Case notes summarizer',
  ])
  await expect(page.locator('.category-label')).toHaveText([
    'Coordinator: hands off to specialists',
    'Coordinator: developer variant',
    'Specialist: works on its own',
    'Specialist: works on its own',
  ])
  await expect(page.locator('.catalog-paths strong')).toHaveText([
    'Use an agent',
    'Create your own',
    'Repository drafts',
  ])
  await page.locator('.catalog-status > summary').click()
  await expect(page.locator('.catalog-status')).toContainText(
    "Automated tests don't call the live model, so check live answers yourself.",
  )
  await expect(page.locator('.catalog-status')).toContainText(
    'Comparing proposals with requirements is in preview',
  )
  await expect(page.locator('.catalog-status')).not.toContainText('PLANNED')
  await expect(page.locator('.catalog-status')).toContainText(
    "They aren't an official Microsoft product.",
  )
  await expect(
    page.locator('.catalog-agent').filter({
      has: page.getByRole('heading', {
        name: 'Checklist and case helper (base setup)',
        exact: true,
      }),
    }),
  ).toContainText('it does not add capabilities')
  for (const item of registry) {
    const card = page.locator('.catalog-agent').filter({
      has: page.getByRole('heading', { name: item.label, exact: true }),
    })
    for (const field of ['input', 'output'] as const)
      await expect(card.locator('.agent-guide')).toContainText(
        item.guidance![field],
      )
    await expect(card.locator('.catalog-human-decision')).toContainText(
      item.guidance!.limits,
    )
    const details = card.locator('.catalog-runtime')
    await expect(details.locator('dl')).toBeHidden()
    await details.locator('summary').click()
    await expect(details).toContainText(item.guidance!.delegation)
    await expect(details.locator('dd')).toHaveText([item.id, item.agent])
    await expect(details).toContainText(
      `${Object.keys(item.tools).length} tool bindings`,
    )
    for (const [tool, target] of Object.entries(item.tools)) {
      await expect(details.locator('li').filter({ hasText: tool })).toHaveText(
        `${tool} to ${target}`,
      )
    }
    await expect(details).toContainText(
      'Configured targets, not execution proof.',
    )
    await expect(details).toContainText('stored receipts are not reverified.')
    await expect(details).toContainText(item.guidance!.configuration)
    await expect(details).toContainText(
      "Editing it does not change a deployed agent's instructions or tools.",
    )
  }
  await page.getByRole('textbox', { name: 'Search agents' }).fill('case notes')
  await expect(page.locator('.catalog-agent h2')).toHaveText([
    'Checklist and case helper',
    'Case notes summarizer',
  ])
  await expectFitsViewport(page)
  expect(state.requests).toHaveLength(0)
})

test('agent guidance remains inspectable without reconfiguring the runtime', async ({
  page,
}, testInfo) => {
  await useNarrowLayout(page)
  const state = await openWorkspace(page)
  const summary = page.locator('.agent-about > summary')
  const guide = page.getByRole('complementary', {
    name: 'Selected agent guide',
  })
  await expect(guide).toBeHidden()
  await summary.click()
  await expect(guide).toBeVisible()
  await expect(guide).toContainText(
    'Your message gives it a task; it does not change its tools or permanent instructions',
  )
  for (const field of ['input', 'output', 'limits', 'delegation'] as const)
    await expect(guide).toContainText(agent.guidance![field])
  expect(
    await guide.evaluate((element) => {
      const { left, right, top, bottom } = element.getBoundingClientRect()
      return (
        left >= 0 && right <= innerWidth && top >= 0 && bottom <= innerHeight
      )
    }),
  ).toBe(true)
  expect(state.requests).toHaveLength(0)
  await screenshot(page, testInfo, 'agent-guide.png')
  await summary.focus()
  await summary.press('Escape')
  await expect(guide).toBeHidden()
  await send(page)
  await summary.click()
  await expect(guide).toContainText(agent.guidance!.output)
  expect(state.requests).toHaveLength(1)
})

test('on a wide screen the agent details sit beside the conversation', async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name === 'mobile',
    'The side column needs a wide window',
  )
  const state = await openWorkspace(page, {
    usage: { input_tokens: 1200, output_tokens: 300, total_tokens: 1500 },
  })
  const nav = workspaceNav(page)
  const aside = page.getByRole('complementary', { name: 'Agent details' })
  const detail = (name: string) =>
    aside
      .locator('.aside-rows > div')
      .filter({ has: page.getByText(name, { exact: true }) })
  await expect(aside.getByRole('heading', { level: 2 })).toHaveText([
    'About this agent',
    'This conversation',
    'Next steps',
  ])
  await expect(aside).toContainText(agent.description)
  await expect(aside).toContainText(agent.guidance!.input)
  await expect(aside).toContainText(agent.guidance!.output)
  // The pop-up in the top bar gives way to the column.
  await expect(page.locator('.agent-about > summary')).toBeHidden()
  await expect(detail('Reply limit')).toContainText('0 of 11 used')
  await expect(detail('Last reply took')).toHaveCount(0)
  await expect(detail('Characters')).toBeVisible()
  await expect(
    aside.getByRole('button', { name: 'Export conversation' }),
  ).toBeDisabled()

  await send(page)
  await expect(detail('Reply limit')).toContainText('1 of 11 used')
  await expect(detail('Last reply took')).toContainText('1.0 s')
  await expect(detail('Tokens')).toContainText('1,200 in · 300 out')
  // Token counts and limits stay under the hood; the reply time doesn't.
  const hood = hoodSwitch(page)
  await hood.uncheck()
  await expect(detail('Tokens')).toBeHidden()
  await expect(detail('Characters')).toBeHidden()
  await expect(detail('Last reply took')).toBeVisible()
  await hood.check()
  await expect(detail('Tokens')).toBeVisible()
  await expect(
    aside.getByRole('button', { name: 'Export conversation' }),
  ).toBeEnabled()
  await aside.getByRole('button', { name: 'Save to shared history' }).click()
  await expect.poll(() => state.saves.length).toBe(1)

  await aside.locator('.aside-more > summary').click()
  const more = aside.locator('.aside-more-body .agent-guide')
  await expect(more).toBeVisible()
  await expect(more).toContainText(agent.guidance!.limits)
  await expect(more).toContainText(agent.guidance!.delegation)
  await screenshot(page, testInfo, 'chat-aside.png')

  await nav.getByRole('button', { name: 'Performance', exact: true }).click()
  await expect(aside).toBeHidden()
  await nav.getByRole('button', { name: 'Chat', exact: true }).click()
  await expect(aside).toBeVisible()
  await page.setViewportSize({ width: 900, height: 900 })
  await expect(aside).toBeHidden()
  await expect(page.locator('.agent-about > summary')).toBeVisible()
})

test('configuration guidance separates UI settings from deployed agent behavior', async ({
  page,
}, testInfo) => {
  const state = await openWorkspace(page)
  await openLibraryTab(page, /^Ready to chat/)
  const guide = page.locator('.configuration-guide')
  await guide.locator(':scope > summary').click()
  await expect(guide).toContainText(
    "Agent creation isn't turned on in this Lab",
  )
  await expect(guide).toContainText('Examples only fill the message box')
  await expect(guide.locator('.configuration-sources dl')).toBeHidden()
  await guide.locator('.configuration-sources > summary').click()
  await expect(guide).toContainText('workbench\\agents.json')
  await expect(guide).toContainText('rebuild and redeploy the Lab')
  await expect(guide).toContainText('publish and test a new agent version')
  await expect(guide).toContainText('they do not register runtime tools')
  for (const setting of [
    'visible_agents',
    'default_agent',
    'workspace_title',
    'WORKBENCH_VISIBLE_AGENTS',
    'WORKBENCH_DEFAULT_AGENT',
    'WORKBENCH_TITLE',
  ])
    await expect(
      guide.locator('code').filter({ hasText: new RegExp(`^${setting}$`) }),
    ).toBeVisible()
  await expect(page.getByRole('textbox')).toHaveCount(1)
  await expect(page.locator('.catalog-agent')).toHaveCount(1)
  if (testInfo.project.name === 'desktop')
    expect(
      (await page.locator('.catalog-agent').boundingBox())!.width,
    ).toBeGreaterThanOrEqual(500)
  await screenshot(page, testInfo, 'configuration-guide.png')
  expect(state.requests).toHaveLength(0)
})

test('legacy catalogs without guidance remain usable without invented capabilities', async ({
  page,
}) => {
  await openWorkspace(page, {
    config: { agents: [{ ...agent, guidance: undefined }] },
  })
  await expect(page.locator('.chat-welcome')).toContainText(
    'This agent has no getting-started guide',
  )
  await expect(
    page.getByRole('button', {
      name: 'Check against a checklist',
      exact: true,
    }),
  ).toBeEnabled()
})

test('guidance accepts the server limit of 1200 Unicode characters', async ({
  page,
}) => {
  const input = '\u{1F600}'.repeat(1200)
  await openWorkspace(page, {
    config: { agents: [{ ...agent, guidance: { ...agent.guidance!, input } }] },
  })
  await expect(page.locator('.chat-welcome .agent-guide')).toContainText(input)
  await expect(page.getByRole('alert')).toHaveCount(0)
})
