import type { Page } from '@playwright/test'

export const themeKey = 'ai-foundry-lab-theme'
export const lightSurface = 'rgb(255, 255, 255)'
export const darkSurface = 'rgb(41, 41, 41)'

// Saves an appearance before the app loads, as a returning visitor would have.
// A string is stored as written so tests can seed unreadable values.
export function seedAppearance(
  target: { addInitScript: Page['addInitScript'] },
  appearance: object | string,
) {
  const value =
    typeof appearance === 'string' ? appearance : JSON.stringify(appearance)
  return target.addInitScript(
    ([key, saved]) => localStorage.setItem(key, saved),
    [themeKey, value],
  )
}

export function computed(page: Page, selector: string, property: string) {
  return page
    .locator(selector)
    .first()
    .evaluate(
      (element, name) => getComputedStyle(element).getPropertyValue(name),
      property,
    )
}

export function contrastAgainstBackground(page: Page, selector: string) {
  return page.locator(selector).evaluateAll((elements) => {
    const luminance = (color: string) => {
      const [r, g, b] = color
        .match(/[\d.]+/g)!
        .slice(0, 3)
        .map(Number)
      const linear = (value: number) => {
        const normalized = value / 255
        return normalized <= 0.04045
          ? normalized / 12.92
          : ((normalized + 0.055) / 1.055) ** 2.4
      }
      return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)
    }
    return Math.min(
      ...elements.map((element) => {
        let back: Element | null = element
        while (
          back &&
          getComputedStyle(back).backgroundColor === 'rgba(0, 0, 0, 0)'
        )
          back = back.parentElement
        const text = luminance(getComputedStyle(element).color)
        const fill = luminance(getComputedStyle(back!).backgroundColor)
        return (Math.max(text, fill) + 0.05) / (Math.min(text, fill) + 0.05)
      }),
    )
  })
}
