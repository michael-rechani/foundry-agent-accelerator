import { type Page, expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { guidedReview, registry } from './fixtures'
import { openWorkspace, send } from './helpers/chat-lab'
import { creationCapability } from './helpers/lab-config'

const caseHelper = registry.find((item) => item.id === 'case-review')!
const twoAgents = { agents: [guidedReview, caseHelper] }

// Start without stored choices, as a first-time visitor would.
test.use({ storageState: { cookies: [], origins: [] } })

const editor = (page: Page) =>
  page.getByRole('textbox', { name: 'Message', exact: true })
const choices = (page: Page) =>
  page.locator('.welcome-modes').getByRole('button')

test('chat opens clean, with no agent details, and sends nothing', async ({
  page,
}) => {
  const state = await openWorkspace(page, { config: twoAgents, startup: true })
  await expect(page.locator('.chat-welcome h1')).toHaveText(
    'What agent do you want to build?',
  )
  await expect(choices(page)).toHaveText([/Try a pre-built agent/])
  await expect(page.locator('.chat-welcome')).not.toContainText(
    guidedReview.label,
  )
  await expect(page.locator('.chat-welcome .welcome-kind')).toHaveCount(0)
  await expect(page.locator('.environment-badge')).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: 'Presenter view' }),
  ).toHaveCount(0)
  await expect(page.locator('.prompt-options')).toHaveCount(0)
  await expect(page.locator('.chat-aside')).toHaveCount(0)
  await expect(page.getByText('About this agent')).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: 'Save to shared history' }),
  ).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: /Choose an agent/ }),
  ).toBeVisible()
  await expect(editor(page)).toHaveAttribute(
    'placeholder',
    /Describe the agent you want to build/,
  )
  expect(state.requests).toEqual([])
})

test('Try a pre-built agent opens the agent picker', async ({ page }) => {
  await openWorkspace(page, { config: twoAgents, startup: true })
  await choices(page).first().click()
  await expect(page.getByPlaceholder('Search agents')).toBeVisible()
})

test('the guide and examples open inside the clean chat', async ({ page }) => {
  const state = await openWorkspace(page, { config: twoAgents, startup: true })
  const toggle = page.getByRole('button', {
    name: 'Show agent guide and examples',
  })
  await toggle.click()
  await expect(page.locator('.chat-welcome h1')).toHaveText(
    'What agent do you want to build?',
  )
  await expect(
    page.getByRole('heading', { name: 'What you can do' }),
  ).toBeVisible()
  await expect(page.getByText('About this agent')).toHaveCount(0)
  await expect(page.locator('.chat-aside')).toHaveCount(0)
  await page.getByRole('button', { name: /Help me design an agent/ }).click()
  await expect(editor(page)).toHaveValue(/Help me design an agent/)
  await page.getByRole('button', { name: 'Hide guide and examples' }).click()
  await expect(page.locator('.prompt-options')).toHaveCount(0)
  await page.reload()
  await expect(page.locator('.chat-welcome h1')).toHaveText(
    'What agent do you want to build?',
  )
  expect(state.requests).toEqual([])
})

test('a saved full view can still return to the simple view', async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem('ai-foundry-lab-simple-chat', '0'),
  )
  await openWorkspace(page, { config: twoAgents, startup: true })
  await expect(page.locator('.chat-welcome h1')).toHaveText(guidedReview.label)
  await page.getByRole('button', { name: 'Simple view' }).click()
  await expect(page.locator('.chat-welcome h1')).toHaveText(
    'What agent do you want to build?',
  )
})

const withDesigner = {
  ...twoAgents,
  library_preview: {
    enabled: true,
    reason: null,
    agent: 'lab-library-preview',
  },
}

test('a first message chats with the Agent designer and stays clean', async ({
  page,
}) => {
  const state = await openWorkspace(page, {
    config: withDesigner,
    startup: true,
    answer: 'Good morning! What would you like to build?',
  })
  await expect(page.locator('#chat-privacy')).toHaveText(
    'Sample data only. AI use may cost money. Saved chats are shared.',
  )
  await expect(page.locator('.composer-privacy details')).not.toHaveAttribute(
    'open',
    '',
  )
  await editor(page).fill('Good morning')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.assistant-message')).toContainText(
    'What would you like to build?',
  )
  expect(state.requests.map((item) => item.agent_id)).toEqual([
    'library-agent-designer',
  ])
  await expect(page.locator('.assistant-heading')).toContainText(
    'Agent designer',
  )
  await expect(page.locator('.chat-aside')).toHaveCount(0)
  await expect(page.getByText('About this agent')).toHaveCount(0)
  await expect(page.locator('.answer-details')).toHaveCount(0)
  await expect(page.locator('.review-note')).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: /Agent designer/ }).first(),
  ).toBeVisible()
  await expect(editor(page)).toHaveAttribute('placeholder', 'Reply...')
  await expect(
    page.getByRole('button', { name: 'Continue in a new chat' }),
  ).toHaveCount(0)
  await expect(page.locator('.save-state')).toHaveText('Not saved')
  await expect(
    page.getByRole('button', { name: 'Save to shared history' }),
  ).toBeEnabled()
  await expect(
    page.getByRole('button', { name: 'Export conversation' }),
  ).toBeEnabled()
  await expect(
    page.getByRole('button', { name: /Choose an agent/ }),
  ).toHaveCount(0)
})

test('designer privacy details stay collapsed but describe shared services', async ({
  page,
}) => {
  const state = await openWorkspace(page, {
    config: {
      ...withDesigner,
      reviews_enabled: true,
      agent_creation: creationCapability(),
    },
    startup: true,
  })
  const privacy = page.locator('.composer-privacy')
  const details = privacy.locator('details')
  const summary = privacy.getByText('Privacy & sharing')
  await expect(page.locator('#chat-privacy')).toHaveText(
    'Sample data only. AI use may cost money. Saved chats are shared.',
  )
  await expect(details).not.toHaveAttribute('open', '')
  await summary.click()
  await expect(privacy).toContainText('No personal or confidential data.')
  await expect(privacy).toContainText(
    'Anyone with Lab access can read, edit and delete saved chats, and read reviews and add requested evidence.',
  )
  await expect(privacy).toContainText(
    'Agent setups are shared. Publishing or deleting an agent requires an operator key, not a user account.',
  )
  await expect(privacy).toContainText(
    'Saved chats contain completed messages and expire 30 days after their last update.',
  )
  await summary.press('Enter')
  await expect(details).not.toHaveAttribute('open', '')
  expect(state.requests).toEqual([])
})

test('the Agent designer can end with a downloadable agent spec', async ({
  page,
}) => {
  const spec = {
    name: 'Renewal Checklist Helper',
    summary: 'Turns a renewal notice into a short checklist.',
    instructions: 'List what the person must send before the renewal date.',
    inputs: 'A renewal notice',
    outputs: 'A checklist',
    tools_needed: [],
    human_decision: 'A caseworker decides eligibility.',
    closest_template: null,
  }
  await openWorkspace(page, {
    config: withDesigner,
    startup: true,
    answer: `Here is the idea.\n\n\`\`\`agent-spec\n${JSON.stringify(spec)}\n\`\`\`\n`,
  })
  await editor(page).fill('Help people renew benefits')
  await page.getByRole('button', { name: 'Send message' }).click()
  const card = page.getByRole('region', { name: 'Agent spec' })
  await expect(card).toContainText('Renewal Checklist Helper')
  await expect(card).toContainText('A caseworker decides eligibility.')
  await expect(card).toContainText(
    'Draft only: this file uses a model placeholder and configures no tools.',
  )
  await expect(page.locator('.assistant-message')).not.toContainText(
    'agent-spec',
  )
  await expect(page.locator('.assistant-message')).not.toContainText(
    '"instructions"',
  )
  await expect(card.getByRole('button', { name: /Create agent/ })).toHaveCount(
    0,
  )
  await expect(card).toContainText('No built-in template matches this idea')
  const download = page.waitForEvent('download')
  await card.getByRole('button', { name: 'Download agent spec' }).click()
  const file = await download
  expect(file.suggestedFilename()).toBe(
    'renewal-checklist-helper.foundry-agent.json',
  )
})

const bundleSpec = {
  name: 'Renewal Checklist Helper',
  summary: 'Turns a renewal notice into a short checklist.',
  instructions: 'List what the person must send before the renewal date.',
  inputs: 'A renewal notice',
  outputs: 'A checklist',
  tools_needed: [],
  human_decision: 'A caseworker decides eligibility.',
  closest_template: null,
}

async function openBundleCard(page: Page) {
  await openWorkspace(page, {
    config: withDesigner,
    startup: true,
    answer: `Here is the idea.\n\n\`\`\`agent-spec\n${JSON.stringify(bundleSpec)}\n\`\`\`\n`,
  })
  await editor(page).fill('Help people renew benefits')
  await page.getByRole('button', { name: 'Send message' }).click()
  const card = page.getByRole('region', { name: 'Agent spec' })
  await expect(card).toContainText('Renewal Checklist Helper')
  return card
}

test('the spec card downloads a hosted agent bundle built by the Lab', async ({
  page,
}, testInfo) => {
  const card = await openBundleCard(page)
  const zip = Buffer.from([0x50, 0x4b, 0x03, 0x04, 0x01, 0x02])
  const requests: { headers: Record<string, string>; body: unknown }[] = []
  await page.route('**/api/agent-bundles', (route) => {
    const request = route.request()
    expect(request.method()).toBe('POST')
    requests.push({ headers: request.headers(), body: request.postDataJSON() })
    return route.fulfill({
      status: 200,
      contentType: 'application/zip',
      body: zip,
    })
  })
  await expect(card).toContainText('Nothing is published from here.')
  const download = page.waitForEvent('download')
  await card
    .getByRole('button', { name: 'Download hosted agent bundle' })
    .click()
  const file = await download
  expect(file.suggestedFilename()).toBe(
    'renewal-checklist-helper.agent-bundle.zip',
  )
  const saved = testInfo.outputPath('bundle.zip')
  await file.saveAs(saved)
  expect(await readFile(saved)).toEqual(zip)
  expect(requests).toHaveLength(1)
  expect(requests[0].headers['x-workbench-request']).toBe('1')
  expect(requests[0].body).toEqual({
    name: 'renewal-checklist-helper',
    description: bundleSpec.summary,
    instructions: bundleSpec.instructions,
  })
  await expect(card.getByRole('alert')).toHaveCount(0)
})

test('a spec the Lab will not bundle shows why and keeps the button usable', async ({
  page,
}) => {
  const card = await openBundleCard(page)
  let downloads = 0
  page.on('download', () => downloads++)
  await page.route('**/api/agent-bundles', (route) =>
    route.fulfill({
      status: 400,
      json: { error: 'invalid_bundle', request_id: 'bundle-request-1' },
    }),
  )
  const button = card.getByRole('button', {
    name: 'Download hosted agent bundle',
  })
  await button.click()
  const alert = card.getByRole('alert')
  await expect(alert).toContainText('did not accept this spec')
  await expect(alert).toContainText('Reference: bundle-request-1')
  await expect(button).toBeEnabled()
  expect(downloads).toBe(0)
})

test('designer conversation exports and survives saving, reopening, updating and deletion', async ({
  page,
}, testInfo) => {
  const spec = {
    name: 'Policy Q&A',
    summary: 'Answers questions from fictional policies.',
    instructions:
      'Quote only the supplied policy text and flag unsupported answers.',
    inputs: 'One or more fictional policy documents',
    outputs: 'Answers with supporting quotes',
    tools_needed: ['document retrieval / search'],
    human_decision: 'A policy owner resolves conflicts and exceptions.',
    closest_template: null,
  }
  const state = await openWorkspace(page, {
    config: withDesigner,
    startup: true,
    receipts: [],
    answers: [
      'Should it use one policy or several?',
      `Here is the draft.\n\n\`\`\`agent-spec\n${JSON.stringify(spec)}\n\`\`\``,
      'A person should verify unsupported answers.',
    ],
  })
  await send(
    page,
    'I want an agent that answers questions from a policy document.',
  )
  await send(page, 'Use one or several fictional policies.')
  expect(state.saves).toEqual([])
  await expect(page.getByRole('region', { name: 'Agent spec' })).toContainText(
    'Policy Q&A',
  )
  const specCard = page.getByRole('region', { name: 'Agent spec' })
  await expect(specCard).toContainText('document retrieval / search')
  await expect(specCard).toContainText(
    'does not configure the listed lookups or document sources',
  )
  await page.screenshot({
    path: testInfo.outputPath('designer-save-export.png'),
    fullPage: true,
    animations: 'disabled',
  })
  await page.getByRole('button', { name: /^Shared history/ }).click()
  await expect(page.getByText('No saved conversations')).toBeVisible()
  await expect(
    page.getByText('Chats are not saved automatically.', { exact: false }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Return to Chat' }).click()
  await expect(page.locator('.assistant-message')).toHaveCount(2)
  await expect(page.getByRole('region', { name: 'Agent spec' })).toContainText(
    'Policy Q&A',
  )

  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect(page.locator('.save-state')).toHaveText('Saved / shared')
  expect(state.saves).toHaveLength(1)
  expect(state.document?.agent_id).toBe('library-agent-designer')
  expect(
    state.document?.turns.every(
      (turn) => turn.result.agent === 'lab-library-preview',
    ),
  ).toBe(true)
  await editor(page).fill('Unsent follow-up for the local export.')
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export conversation' }).click()
  const file = await download
  expect(file.suggestedFilename()).toBe('foundry-conversation.json')
  const exportPath = testInfo.outputPath('designer-conversation.json')
  await file.saveAs(exportPath)
  const exported = JSON.parse(await readFile(exportPath, 'utf8'))
  expect(exported.turns).toEqual(state.document?.turns)
  expect(exported.turns[1].result.text).toContain(JSON.stringify(spec))
  expect(exported.draft).toBe('Unsent follow-up for the local export.')
  expect(state.requests).toHaveLength(2)
  expect(state.saves).toHaveLength(1)

  await editor(page).fill('')
  await page.reload()
  await page.getByRole('button', { name: /^Shared history/ }).click()
  await expect(page.locator('.saved-open')).toContainText('Agent designer')
  await page.locator('.saved-open').click()
  await expect(page.locator('.assistant-message')).toHaveCount(2)
  await expect(page.getByRole('region', { name: 'Agent spec' })).toContainText(
    'Policy Q&A',
  )
  await expect(page.locator('.save-state')).toHaveText('Saved / shared')
  await expect(
    page.getByRole('button', { name: 'Save to shared history' }),
  ).toBeDisabled()
  expect(state.requests).toHaveLength(2)
  await send(
    page,
    'What should happen when a policy does not support an answer?',
  )
  expect(state.requests[2].history.map((message) => message.role)).toEqual([
    'user',
    'assistant',
    'user',
    'assistant',
  ])
  await page.getByRole('button', { name: 'Save to shared history' }).click()
  await expect(page.locator('.save-state')).toHaveText('Saved / shared')
  expect(state.updates).toEqual(['v1'])
  expect(state.document?.turns).toHaveLength(3)
  await page.getByRole('button', { name: /^Shared history/ }).click()
  await page.getByRole('button', { name: /^Delete I want an agent/ }).click()
  await page.getByRole('button', { name: 'Delete for everyone' }).click()
  await expect(page.getByText('No saved conversations')).toBeVisible()
  expect(state.deletes).toEqual(['v2'])
})

test('designer export stays available when shared history is disabled', async ({
  page,
}) => {
  const state = await openWorkspace(page, {
    config: { ...withDesigner, history_enabled: false },
    startup: true,
    receipts: [],
  })
  await editor(page).fill('Help me design an agent using fictional policies.')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.assistant-message')).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Save to shared history' }),
  ).toBeDisabled()
  await expect(
    page.getByRole('button', { name: 'Save to shared history' }),
  ).toHaveAttribute('title', /Shared history is unavailable/)
  await expect(
    page.getByRole('button', { name: 'Export conversation' }),
  ).toBeEnabled()
  expect(state.saves).toEqual([])
})

test('from the Agent designer the person can move to a real agent', async ({
  page,
}) => {
  const state = await openWorkspace(page, {
    config: withDesigner,
    startup: true,
  })
  await editor(page).fill('Hello')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.assistant-message')).toBeVisible()
  await page.locator('.agent-picker').click()
  const picker = page.getByRole('dialog', { name: 'Choose an agent' })
  await expect(
    picker.getByRole('region', { name: 'General chat' }),
  ).toContainText('Agent designer')
  await picker
    .getByRole('button', { name: new RegExp(caseHelper.label) })
    .click()
  await page.getByRole('button', { name: 'Switch agent' }).click()
  await editor(page).fill('Review synthetic APP-1')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.chat-aside')).toBeVisible()
  expect(state.requests.map((item) => item.agent_id)).toEqual([
    'library-agent-designer',
    caseHelper.id,
  ])
})

test('without library previews the first message goes to the default agent', async ({
  page,
}) => {
  const state = await openWorkspace(page, { config: twoAgents, startup: true })
  await editor(page).fill('Good morning')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.assistant-message')).toBeVisible()
  expect(state.requests.map((item) => item.agent_id)).toEqual([guidedReview.id])
})
