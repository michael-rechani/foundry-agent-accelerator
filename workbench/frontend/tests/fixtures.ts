import { readFile } from 'node:fs/promises'
import type { Page, TestInfo } from '@playwright/test'
import type { Agent } from '../src/workspace-config'

export const registry: Agent[] = JSON.parse(
  await readFile(new URL('../../agents.json', import.meta.url), 'utf8'),
)
export const guidedReview = registry.find(
  (item) => item.id === 'customer-review',
)!

export async function illustrativeScreenshot(
  page: Page,
  testInfo: TestInfo,
  filename: string,
  watermark: 'corner' | 'sidebar' = 'corner',
) {
  await page.evaluate((watermark) => {
    const label = document.createElement('div')
    label.dataset.illustrativeScreenshot = 'true'
    label.textContent =
      'ILLUSTRATIVE UI TEST - mocked APIs; no live model results or saved records'
    label.style.cssText =
      'position:fixed;bottom:8px;right:8px;z-index:1000;max-width:calc(100vw - 16px);padding:8px 12px;border-radius:4px;background:#242424;color:white;font:11px/1.5 sans-serif;pointer-events:none'
    if (watermark === 'sidebar' && innerWidth >= 1000) {
      label.style.right = 'auto'
      label.style.left = '8px'
      label.style.bottom = '104px'
      label.style.maxWidth = '200px'
    }
    document.body.append(label)
  }, watermark)
  try {
    await page.screenshot({
      path: testInfo.outputPath(filename),
      fullPage: true,
      animations: 'disabled',
    })
  } finally {
    await page
      .locator('[data-illustrative-screenshot]')
      .evaluate((element) => element.remove())
  }
}
