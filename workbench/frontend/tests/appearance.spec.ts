import { expect, test } from '@playwright/test'
import {
  computed,
  darkSurface,
  lightSurface,
  seedAppearance,
  themeKey,
} from './helpers/appearance'
import { openCreation } from './helpers/creation-lab'
import {
  expectFitsViewport,
  fitsViewport,
  useNarrowLayout,
} from './helpers/layout'
import { openChat } from './helpers/navigation'
import { looks } from '../src/theme'

test('appearance follows the device by default and applies saved choices everywhere', async ({
  page,
}, testInfo) => {
  await openCreation(page)
  const root = page.locator('html')
  await expect(root).toHaveAttribute('data-theme', 'system')
  await expect(root).toHaveAttribute('data-accent', 'foundry')
  await expect(root).toHaveAttribute('data-look', 'classic')
  expect(await computed(page, '.chat-topbar', 'background-color')).toBe(
    lightSurface,
  )
  await page.emulateMedia({ colorScheme: 'dark' })
  expect(await computed(page, '.chat-topbar', 'background-color')).toBe(
    darkSurface,
  )
  await page.emulateMedia({ colorScheme: 'light' })

  const control = page.getByTitle('Appearance', { exact: true })
  const panel = page.getByRole('complementary', {
    name: 'Appearance settings',
  })
  await control.click()
  await expect(panel).toBeInViewport()
  expect(
    await panel.evaluate((element) => {
      const { left, right } = element.getBoundingClientRect()
      return left >= 0 && right <= innerWidth
    }),
  ).toBe(true)
  await expect(page.getByRole('radio', { name: 'System' })).toBeChecked()
  await expect(page.getByRole('radio', { name: 'Foundry' })).toBeChecked()
  await expect(page.getByRole('radio', { name: 'Classic' })).toBeChecked()

  await page.getByRole('radio', { name: 'Dark' }).check()
  await expect(root).toHaveAttribute('data-theme', 'dark')
  expect(await computed(page, '.chat-topbar', 'background-color')).toBe(
    darkSurface,
  )
  await page.getByRole('radio', { name: 'Orchid' }).check()
  await expect(root).toHaveAttribute('data-accent', 'orchid')
  await page.screenshot({ path: testInfo.outputPath('appearance.png') })
  expect(await computed(page, '.creation-primary', 'background-color')).toBe(
    'rgb(140, 28, 106)',
  )
  expect(
    JSON.parse(
      (await page.evaluate((key) => localStorage.getItem(key), themeKey))!,
    ),
  ).toEqual({ mode: 'dark', accent: 'orchid', look: 'classic' })
  await page.keyboard.press('Escape')
  await expect(panel).toBeHidden()
  await expect(control).toBeFocused()

  await page.reload()
  await expect(root).toHaveAttribute('data-theme', 'dark')
  await expect(root).toHaveAttribute('data-accent', 'orchid')
  await openChat(page)
  expect(await computed(page, '.chat-topbar', 'background-color')).toBe(
    darkSurface,
  )
  await control.click()
  await expect(page.getByRole('radio', { name: 'Dark' })).toBeChecked()
  await expect(page.getByRole('radio', { name: 'Orchid' })).toBeChecked()

  await page.evaluate((key) => {
    const value = JSON.stringify({
      mode: 'light',
      accent: 'lagoon',
      look: 'console',
    })
    localStorage.setItem(key, value)
    dispatchEvent(new StorageEvent('storage', { key, newValue: value }))
  }, themeKey)
  await expect(root).toHaveAttribute('data-theme', 'light')
  await expect(root).toHaveAttribute('data-accent', 'lagoon')
  await expect(root).toHaveAttribute('data-look', 'console')
  await expect(page.getByRole('radio', { name: 'Lagoon' })).toBeChecked()
  await expect(page.getByRole('radio', { name: 'Console' })).toBeChecked()
  await expectFitsViewport(page)
})

test('header panels open one at a time so none is hidden behind another', async ({
  page,
}) => {
  await useNarrowLayout(page)
  await openCreation(page)
  await openChat(page)
  const appearance = page.getByRole('complementary', {
    name: 'Appearance settings',
  })
  const guide = page.getByRole('complementary', {
    name: 'Selected agent guide',
  })
  const onTop = (panel: typeof appearance) =>
    panel.evaluate((element) => {
      const { left, top, width } = element.getBoundingClientRect()
      return element.contains(
        document.elementFromPoint(left + width / 2, top + 16),
      )
    })

  await page.getByTitle('Appearance', { exact: true }).click()
  await expect(appearance).toBeInViewport()
  expect(await onTop(appearance)).toBe(true)

  await page.locator('.agent-about > summary').click()
  await expect(guide).toBeInViewport()
  await expect(appearance).toBeHidden()
  expect(await onTop(guide)).toBe(true)

  await page.getByTitle('Appearance', { exact: true }).click()
  await expect(appearance).toBeInViewport()
  await expect(guide).toBeHidden()
  expect(await onTop(appearance)).toBe(true)
})

test('unreadable saved appearance falls back to the defaults', async ({
  page,
}) => {
  await seedAppearance(page, '{"mode":"neon","accent":42,"look":"neon"}')
  await openCreation(page)
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'system')
  await expect(page.locator('html')).toHaveAttribute('data-accent', 'foundry')
  await expect(page.locator('html')).toHaveAttribute('data-look', 'classic')
  await page.evaluate((key) => localStorage.setItem(key, 'not json'), themeKey)
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'system')
  await expect(page.locator('html')).toHaveAttribute('data-accent', 'foundry')
  await expect(page.locator('html')).toHaveAttribute('data-look', 'classic')
})

test('an appearance saved before looks existed opens in Classic', async ({
  page,
}) => {
  await seedAppearance(page, '{"mode":"dark","accent":"orchid"}')
  await openCreation(page)
  const root = page.locator('html')
  await expect(root).toHaveAttribute('data-theme', 'dark')
  await expect(root).toHaveAttribute('data-accent', 'orchid')
  await expect(root).toHaveAttribute('data-look', 'classic')
  await page.getByTitle('Appearance', { exact: true }).click()
  await expect(page.getByRole('radio', { name: 'Classic' })).toBeChecked()
  await expect(page.getByRole('radio', { name: 'Dark' })).toBeChecked()
  await expect(page.getByRole('radio', { name: 'Orchid' })).toBeChecked()
})

test('each look restyles the app at once and is remembered with the other choices', async ({
  page,
}) => {
  await openCreation(page)
  const root = page.locator('html')
  const control = page.getByTitle('Appearance', { exact: true })
  const lookToken = () =>
    page.evaluate(() =>
      getComputedStyle(document.documentElement)
        .getPropertyValue('--look-glass')
        .trim(),
    )
  const saved = async () =>
    JSON.parse(
      (await page.evaluate((key) => localStorage.getItem(key), themeKey))!,
    )
  const fits = () => fitsViewport(page)

  await control.click()
  await expect(
    page.getByRole('group', { name: 'Look' }).getByRole('radio'),
  ).toHaveCount(looks.length)
  // A reload would clear this marker, so it proves a look changes in place.
  await page.evaluate(() => (document.documentElement.dataset.marker = 'kept'))
  expect(await lookToken()).toBe('')
  expect(await computed(page, '.theme-panel', 'border-radius')).toBe('12px')

  await page.getByRole('radio', { name: 'Aurora' }).check()
  await expect(root).toHaveAttribute('data-look', 'aurora')
  expect(await lookToken()).not.toBe('')
  expect(await computed(page, '.theme-panel', 'border-radius')).toBe('14px')
  expect(await saved()).toEqual({
    mode: 'system',
    accent: 'foundry',
    look: 'aurora',
  })
  expect(await fits()).toBe(true)

  await page.getByRole('radio', { name: 'Console' }).check()
  await expect(root).toHaveAttribute('data-look', 'console')
  expect(await lookToken()).toBe('')
  expect(await computed(page, '.theme-panel', 'border-radius')).toBe('2px')
  expect(await fits()).toBe(true)

  await page.getByRole('radio', { name: 'Dark' }).check()
  await page.getByRole('radio', { name: 'Lagoon' }).check()
  await expect(root).toHaveAttribute('data-theme', 'dark')
  await expect(root).toHaveAttribute('data-accent', 'lagoon')
  await expect(root).toHaveAttribute('data-look', 'console')
  await expect(root).toHaveAttribute('data-marker', 'kept')
  expect(await saved()).toEqual({
    mode: 'dark',
    accent: 'lagoon',
    look: 'console',
  })

  await page.reload()
  await expect(root).toHaveAttribute('data-theme', 'dark')
  await expect(root).toHaveAttribute('data-accent', 'lagoon')
  await expect(root).toHaveAttribute('data-look', 'console')
  await control.click()
  await expect(page.getByRole('radio', { name: 'Dark' })).toBeChecked()
  await expect(page.getByRole('radio', { name: 'Lagoon' })).toBeChecked()
  await expect(page.getByRole('radio', { name: 'Console' })).toBeChecked()

  await page.getByRole('radio', { name: 'Classic' }).check()
  await expect(root).toHaveAttribute('data-look', 'classic')
  expect(await lookToken()).toBe('')
  expect(await computed(page, '.theme-panel', 'border-radius')).toBe('12px')
  expect(await saved()).toEqual({
    mode: 'dark',
    accent: 'lagoon',
    look: 'classic',
  })
})

test('the appearance panel scrolls inside a short window so every look stays reachable', async ({
  page,
}) => {
  await openCreation(page)
  await page.setViewportSize({ width: page.viewportSize()!.width, height: 420 })
  await page.getByTitle('Appearance', { exact: true }).click()
  const panel = page.getByRole('complementary', {
    name: 'Appearance settings',
  })
  await expect(panel).toBeInViewport()
  expect(
    await panel.evaluate((element) => {
      const { top, bottom } = element.getBoundingClientRect()
      return top >= 0 && bottom <= innerHeight
    }),
  ).toBe(true)
  expect(
    await panel.evaluate(
      (element) => element.scrollHeight > element.clientHeight,
    ),
  ).toBe(true)
  await page.getByRole('radio', { name: 'Console' }).check()
  await expect(page.locator('html')).toHaveAttribute('data-look', 'console')
  await expect(page.getByRole('radio', { name: 'Console' })).toBeInViewport()
})
