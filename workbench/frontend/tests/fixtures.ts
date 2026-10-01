import { readFile } from 'node:fs/promises'
import type { Page, TestInfo } from '@playwright/test'
import type { Agent } from '../src/workspace-config'

export const registry: Agent[] = JSON.parse(
  await readFile(new URL('../../agents.json', import.meta.url), 'utf8'),
)
export const guidedReview = registry.find(
  (item) => item.id === 'customer-review',
)!

export async function screenshot(
  page: Page,
  testInfo: TestInfo,
  filename: string,
) {
  await page.screenshot({
    path: testInfo.outputPath(filename),
    fullPage: true,
    animations: 'disabled',
  })
}

// README and docs pictures show the plain view a first-time visitor sees.
// Desktop specs start with Under the hood on, so switch it off for the picture
// and back on afterwards.
export async function docsScreenshot(
  page: Page,
  testInfo: TestInfo,
  filename: string,
) {
  if (testInfo.project.name !== 'desktop')
    return screenshot(page, testInfo, filename)
  const hood = page.getByRole('switch', { name: /Under the hood/ })
  const wasOn = await hood.isChecked()
  if (wasOn) await hood.uncheck()
  await page.evaluate(() => (document.activeElement as HTMLElement)?.blur())
  await page.mouse.move(0, 0)
  try {
    await screenshot(page, testInfo, filename)
  } finally {
    if (wasOn) await hood.check()
  }
}
