import { expect, type Page } from '@playwright/test'

export const fitsViewport = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)

export async function expectFitsViewport(page: Page) {
  expect(await fitsViewport(page)).toBe(true)
}

// Wide windows move the agent guide to a right-hand column. Use the narrower
// layout, where the header holds the guide, appearance and lab panels.
export async function useNarrowLayout(page: Page) {
  if ((page.viewportSize()?.width ?? 0) >= 1000)
    await page.setViewportSize({ width: 900, height: 900 })
}
