import { expect, test } from '@playwright/test'
import { docsScreenshot, screenshot } from './fixtures'
import { seedAppearance } from './helpers/appearance'
import { invoice, support, templates } from './helpers/catalog'
import { expectFitsViewport } from './helpers/layout'
import { openAgent, openLibrary } from './helpers/library-lab'
import { libraryNav } from './helpers/navigation'

for (const mode of ['light', 'dark'] as const)
  test(`library detail is readable in ${mode} mode`, async ({
    page,
  }, testInfo) => {
    await seedAppearance(page, { mode, accent: 'foundry' })
    await openLibrary(page, { ready: true })
    await expect(page.locator('html')).toHaveAttribute('data-theme', mode)
    await openAgent(page, support.label)
    const contrast = await page.locator('.library-lede').evaluate((element) => {
      const luminance = (color: string) => {
        const [r, g, b] = color
          .match(/[\d.]+/g)!
          .slice(0, 3)
          .map((value) => {
            const channel = Number(value) / 255
            return channel <= 0.04045
              ? channel / 12.92
              : ((channel + 0.055) / 1.055) ** 2.4
          })
        return r * 0.2126 + g * 0.7152 + b * 0.0722
      }
      let node: Element | null = element
      let background = 'rgba(0, 0, 0, 0)'
      while (node && /rgba\(.*, 0\)$/.test(background)) {
        background = getComputedStyle(node).backgroundColor
        node = node.parentElement
      }
      const values = [
        luminance(getComputedStyle(element).color),
        luminance(background),
      ].sort((a, b) => b - a)
      return (values[0] + 0.05) / (values[1] + 0.05)
    })
    expect(contrast).toBeGreaterThanOrEqual(4.5)
    await expectFitsViewport(page)
    await screenshot(page, testInfo, `library-detail-${mode}.png`)
  })

// The README and docs pictures: the plain view a first-time visitor sees.
for (const mode of ['light', 'dark'] as const)
  test(`the library tour shows Browse, Test results and Take it to Foundry in ${mode} mode`, async ({
    page,
  }, testInfo) => {
    const suffix = mode === 'dark' ? '-dark' : ''
    await seedAppearance(page, { mode, accent: 'foundry' })
    const state = await openLibrary(page)
    await expect(page.locator('html')).toHaveAttribute('data-theme', mode)
    await expect(page.locator('.library-card')).toHaveCount(templates.length)
    await expect(page.getByRole('region', { name: 'Start here' })).toBeVisible()
    await docsScreenshot(page, testInfo, `library-browse${suffix}.png`)

    await openAgent(page, invoice.label)
    const tabs = page.getByRole('tablist', { name: 'Agent details' })
    const panel = page.getByRole('tabpanel')
    await tabs.getByRole('tab', { name: 'Test results' }).click()
    await expect(panel).toContainText('25 of 25 answers passed')
    await expect(panel).toContainText('Waiting for a person')
    await docsScreenshot(page, testInfo, `library-test-results${suffix}.png`)

    await tabs.getByRole('tab', { name: 'Take it to Foundry' }).click()
    await expect(
      panel.getByRole('button', { name: 'Download agent definition' }),
    ).toBeEnabled()
    await docsScreenshot(page, testInfo, `library-take-to-foundry${suffix}.png`)
    // Looking around sends nothing and makes nothing.
    expect(state.chat).toHaveLength(0)
    expect(state.drafts).toBe(0)
    expect(state.creations).toBe(0)
  })

for (const mode of ['light', 'dark'] as const)
  test(`the Add-ons tab shows both groups in ${mode} mode`, async ({
    page,
  }, testInfo) => {
    await seedAppearance(page, { mode, accent: 'foundry' })
    const state = await openLibrary(page)
    await expect(page.locator('html')).toHaveAttribute('data-theme', mode)
    await libraryNav(page).getByRole('button', { name: 'Add-ons' }).click()
    await expect(
      page.getByRole('heading', {
        level: 1,
        name: 'Add-ons an agent could use',
      }),
    ).toBeVisible()
    const cards = page.locator('.addon-card')
    await expect(cards.getByText('Lets an agent do more').first()).toBeVisible()
    await expect(cards.getByText('Supports the agent').first()).toBeVisible()
    await docsScreenshot(
      page,
      testInfo,
      `library-addons${mode === 'dark' ? '-dark' : ''}.png`,
    )
    expect(state.chat).toHaveLength(0)
    expect(state.creations).toBe(0)
    expect(state.drafts).toBe(0)
  })

for (const mode of ['light', 'dark'] as const)
  test(`the Create agent page offers every library template in three groups in ${mode} mode`, async ({
    page,
  }, testInfo) => {
    await seedAppearance(page, { mode, accent: 'foundry' })
    const state = await openLibrary(page, { hash: '#create' })
    await expect(page.locator('html')).toHaveAttribute('data-theme', mode)
    const cards = page.locator('.creation-template')
    await expect(cards).toHaveCount(templates.length)
    await expect(page.locator('.creation-template-group h2')).toHaveText([
      'Works in any sector',
      'Private sector',
      'Healthcare and public sector',
    ])
    if (mode === 'dark') {
      await cards.nth(1).click()
      await expect(page.locator('.creation-template-check')).toHaveCount(1)
    }
    await page.evaluate(() => {
      document.querySelector('.creation-workspace')!.scrollTop = 0
    })
    await docsScreenshot(
      page,
      testInfo,
      `library-create-agent${mode === 'dark' ? '-dark' : ''}.png`,
    )
    expect(state.drafts).toBe(0)
    expect(state.creations).toBe(0)
  })
