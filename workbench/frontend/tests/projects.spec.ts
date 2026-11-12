import { readFile } from 'node:fs/promises'
import { expect, test, type Page } from '@playwright/test'
import { PROJECT_STORAGE_KEY } from '../src/project-brief'
import {
  openCreation,
  operatorKey,
  recordFor,
  templates,
} from './helpers/creation-lab'
import { workspaceNav } from './helpers/navigation'

test.use({ storageState: { cookies: [], origins: [] } })

const spec = {
  name: 'Fictional Notice Helper',
  summary: 'Explains a sample notice and asks for missing dates.',
  instructions:
    'Explain the fictional notice, cite the source and ask for missing dates.',
  inputs: 'A fictional notice',
  outputs: 'A referenced summary',
  tools_needed: [],
  human_decision: 'Staff decide next steps.',
  closest_template: templates[0].id,
}
const designerAnswer = `A draft to review.\n\`\`\`agent-spec\n${JSON.stringify(spec)}\n\`\`\``

async function saveBrief(page: Page) {
  await page.getByLabel('Project name (required)').fill('Notice project')
  await page
    .getByLabel('Goal (required)', { exact: true })
    .fill('Explain fictional notices and identify missing dates.')
  await page
    .getByLabel('Context and boundaries')
    .fill('Use fictional data; no customer systems.')
  await page
    .getByLabel('Decisions and open questions')
    .fill('Staff decide the next action.')
  await page
    .getByLabel('Deliverables and evidence notes')
    .fill('A reviewed draft and test report.')
  await page
    .getByLabel('Sample demonstration prompt')
    .fill('Sample notice: the office opens at 09:00.')
  await page.getByRole('button', { name: 'Save brief in this browser' }).click()
  await expect(
    page.getByText('Loaded from this browser.', { exact: true }),
  ).toBeVisible()
}

async function localData(page: Page) {
  return page.evaluate(
    (key) => JSON.parse(localStorage.getItem(key)!),
    PROJECT_STORAGE_KEY,
  )
}

test('a project goes from brief to designer, consent-gated draft evidence and a ready-agent demonstration', async ({
  page,
}) => {
  const ready = recordFor()
  const state = await openCreation(page, {
    hash: '#projects',
    designerAnswer,
    saved: ready,
  })
  const calls: string[] = []
  await page.route('**/api/agent-test-*', async (route) => {
    const body = route.request().postDataJSON()
    expect(body.confirm_cost).toBe(true)
    expect(
      route.request().headers()['x-workbench-creation-key'],
    ).toBeUndefined()
    const path = new URL(route.request().url()).pathname
    calls.push(path)
    const oneCase = {
      id: 'grounded-hours',
      category: 'grounded',
      input: 'Sample notice: the office opens at 09:00.',
      checks: { must_include: ['09:00'] },
      rubric: 'States the opening hours.',
    }
    await route.fulfill({
      json: path.endsWith('cases')
        ? {
            request_id: 'mock-cases',
            template_id: templates[0].id,
            cases: [oneCase],
            rejected: [],
            elapsed_ms: 10,
          }
        : {
            request_id: 'mock-run',
            case_id: oneCase.id,
            passed: true,
            failures: [],
            text: 'ILLUSTRATIVE ANSWER: The office opens at 09:00.',
            receipts: [],
            elapsed_ms: 10,
          },
    })
  })
  await saveBrief(page)
  expect(state.chat).toEqual([])
  expect(state.drafts).toEqual([])
  expect(state.posts).toEqual([])
  const stored = await localData(page)
  expect(Object.keys(stored.projects[0]).sort()).toEqual([
    'agentId',
    'context',
    'decisions',
    'deliverables',
    'demoPrompt',
    'goal',
    'id',
    'name',
    'updatedAt',
  ])
  await page.getByRole('button', { name: 'Load brief in designer' }).click()
  const message = page.getByRole('textbox', { name: 'Message', exact: true })
  await expect(message).toHaveValue(/Goal:\nExplain fictional notices/)
  expect(state.chat).toEqual([])
  await page.getByRole('button', { name: 'Send message' }).click()
  const card = page.getByRole('region', { name: 'Agent spec' })
  await expect(card).toContainText(spec.name)
  await page.getByRole('button', { name: 'Back to project' }).click()
  await expect(
    page.getByText(/Spec received: Fictional Notice Helper/),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Return to current work' }).click()
  await expect(card).toBeVisible()
  await card.getByRole('button', { name: 'Test this draft first' }).click()
  const panel = card.getByRole('group', { name: 'Test this draft' })
  await expect(
    panel.getByRole('button', { name: 'Write test cases' }),
  ).toBeDisabled()
  expect(calls).toEqual([])
  await panel.getByRole('checkbox').check()
  await panel.getByRole('button', { name: 'Write test cases' }).click()
  await panel
    .getByRole('button', { name: 'Run 1 test call', exact: true })
    .click()
  await expect(panel).toContainText('1 of 1 run passed the automatic checks')
  await page.getByRole('button', { name: 'Back to project' }).click()
  await page.getByLabel('Agent for demonstration').selectOption(ready.id)
  await page.getByRole('button', { name: 'Save brief in this browser' }).click()
  await page.getByRole('button', { name: 'Open demonstration chat' }).click()
  await page
    .getByRole('button', { name: 'Open project conversation', exact: true })
    .click()
  await expect(message).toHaveValue('Sample notice: the office opens at 09:00.')
  expect(state.chat).toHaveLength(1)
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.getByText(/ILLUSTRATIVE ANSWER: NOTICE-2/)).toBeVisible()
  expect(state.chat[1].agent_id).toBe(ready.id)
  await page.getByRole('button', { name: 'Presenter view' }).click()
  await expect(page.locator('.chat-app')).toHaveClass(/presenter-view/)
  expect(state.posts).toEqual([])
  expect((await localData(page)).projects[0]).not.toHaveProperty('transcript')
})

test('a project spec can create and chat with its agent without bypassing consent or losing the project return path', async ({
  page,
}) => {
  const state = await openCreation(page, { hash: '#projects', designerAnswer })
  await saveBrief(page)
  await page.getByRole('button', { name: 'Load brief in designer' }).click()
  await page.getByRole('button', { name: 'Send message' }).click()
  const card = page.getByRole('region', { name: 'Agent spec' })
  await card.getByRole('button', { name: 'Create this agent here' }).click()
  const panel = card.getByRole('group', { name: 'Create this agent' })
  const create = panel.getByRole('button', { name: 'Create in Foundry' })
  await expect(create).toBeDisabled()
  expect(state.posts).toEqual([])
  await panel.getByRole('checkbox').check()
  await create.click()
  await expect(panel.getByRole('alert')).toContainText('operator key')
  expect(state.posts).toEqual([])
  await panel.getByLabel('Operator key', { exact: true }).fill(operatorKey)
  await create.click()
  await expect(card.getByRole('status')).toContainText('is ready in Foundry')
  await card.getByRole('button', { name: /Chat with it/ }).click()
  await page.getByRole('button', { name: 'Switch agent', exact: true }).click()
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Sample notice: the office opens at 09:00.')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.assistant-message').last()).toContainText(
    'ILLUSTRATIVE ANSWER',
  )
  expect(state.chat.at(-1)?.agent_id).toBe(state.record!.id)
  expect(state.keys).toEqual([operatorKey])
  await page.getByRole('button', { name: 'Back to project' }).click()
  await page
    .getByLabel('Agent for demonstration')
    .selectOption(state.record!.id)
  await page.getByRole('button', { name: 'Save brief in this browser' }).click()
  const saved = (await localData(page)).projects[0]
  expect(saved.agentId).toBe(state.record!.id)
  expect(JSON.stringify(saved)).not.toContain(operatorKey)
})

test('briefs survive reload, exports contain only saved notes, and deletion leaves shared agents untouched', async ({
  page,
}) => {
  const state = await openCreation(page, { hash: '#projects', preview: true })
  await expect(
    page.getByRole('button', { name: 'Load brief in designer' }),
  ).toBeDisabled()
  await saveBrief(page)
  await page.reload()
  await expect(page.getByLabel('Project name (required)')).toHaveValue(
    'Notice project',
  )
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export saved brief' }).click()
  const file = await download
  const content = JSON.parse(await readFile((await file.path())!, 'utf8'))
  expect(content.project.name).toBe('Notice project')
  expect(content.storage).toContain('no chats, tests or runtime')
  await page.getByRole('button', { name: 'New project', exact: true }).click()
  await expect(page.getByLabel('Project name (required)')).toHaveValue('')
  await page
    .getByLabel('Project', { exact: true })
    .selectOption({ label: 'Notice project' })
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Delete local brief' }).click()
  expect((await localData(page)).projects).toEqual([])
  expect(state.deletes).toBe(0)
  expect(state.chat).toEqual([])
})

test('storage corruption is visible and cannot be silently overwritten', async ({
  page,
}) => {
  await openCreation(page, { hash: '#projects', preview: true })
  await page.evaluate(
    (key) => localStorage.setItem(key, '{damaged'),
    PROJECT_STORAGE_KEY,
  )
  await page.reload()
  await expect(page.getByRole('alert')).toContainText(
    'Existing storage has not been changed',
  )
  expect(
    await page.evaluate(
      (key) => localStorage.getItem(key),
      PROJECT_STORAGE_KEY,
    ),
  ).toBe('{damaged')
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Forget local projects' }).click()
  await expect(page.getByLabel('Project name (required)')).toBeVisible()
  expect(
    await page.evaluate(
      (key) => localStorage.getItem(key),
      PROJECT_STORAGE_KEY,
    ),
  ).toBeNull()
})

test('failed saves preserve the form and unsaved project switches require confirmation', async ({
  page,
}) => {
  await openCreation(page, { hash: '#projects', preview: true })
  await saveBrief(page)
  await page
    .getByLabel('Goal (required)', { exact: true })
    .fill('Changed fictional goal')
  await page.evaluate(() => {
    Storage.prototype.setItem = () => {
      throw new DOMException('Full', 'QuotaExceededError')
    }
  })
  await page.getByRole('button', { name: 'Save brief in this browser' }).click()
  await expect(page.getByRole('alert')).toContainText(
    'Project changes were not saved',
  )
  await expect(page.getByLabel('Goal (required)', { exact: true })).toHaveValue(
    'Changed fictional goal',
  )
  expect((await localData(page)).projects[0].goal).toBe(
    'Explain fictional notices and identify missing dates.',
  )
  page.once('dialog', (dialog) => dialog.dismiss())
  await page.getByRole('button', { name: 'New project', exact: true }).click()
  await expect(page.getByLabel('Goal (required)', { exact: true })).toHaveValue(
    'Changed fictional goal',
  )
  await expect(
    page.getByRole('button', { name: 'Load brief in designer' }),
  ).toBeDisabled()
})

test('saved missing agents remain unavailable and desktop layouts keep project controls usable', async ({
  page,
}, testInfo) => {
  const ready = recordFor()
  const state = await openCreation(page, {
    hash: '#projects',
    saved: ready,
    designerAnswer,
  })
  await saveBrief(page)
  await page.getByLabel('Agent for demonstration').selectOption(ready.id)
  await page.getByRole('button', { name: 'Save brief in this browser' }).click()
  for (const width of [1440, 1100]) {
    await page.setViewportSize({ width, height: 1000 })
    await expect(
      page.getByRole('button', { name: 'Open demonstration chat' }),
    ).toBeEnabled()
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true)
    await page
      .locator('.project-workspace')
      .evaluate((element) => element.scrollTo(0, 0))
    await page.screenshot({
      path: testInfo.outputPath(`project-${width}.png`),
      fullPage: true,
    })
  }
  state.missingFromList = true
  await page.reload()
  await expect(
    page.getByText('The saved agent is unavailable or no longer ready.', {
      exact: false,
    }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Open demonstration chat' }),
  ).toBeDisabled()
  await workspaceNav(page)
    .getByRole('button', { name: 'Chat', exact: true })
    .click()
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toBeVisible()
})
