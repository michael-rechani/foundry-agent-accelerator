import { type Page, expect, test } from '@playwright/test'
import { screenshot } from './fixtures'
import {
  contrastAgainstBackground,
  seedAppearance,
  themeKey,
} from './helpers/appearance'
import { openCreation, templates } from './helpers/creation-lab'
import { accents, looks } from '../src/theme'

test('every look keeps text, links and buttons readable in light and dark with each accent', async ({
  page,
}) => {
  await openCreation(page)
  const { checked, failures } = await page.evaluate(
    ({ looks, accents }) => {
      const tokens = [
        'bg',
        'bg-deep',
        'surface',
        'surface-subtle',
        'surface-hover',
        'surface-sunken',
        'text',
        'text-secondary',
        'muted',
        'accent',
        'accent-hover',
        'accent-strong',
        'accent-soft',
        'accent-tint',
        'accent-fill',
        'accent-fill-hover',
        'on-accent',
        'field-line',
        'success-fg',
      ]
      type Color = [number, number, number, number]
      const parse = (value: string): Color => {
        const n = value.match(/[\d.]+/g)!.map(Number)
        if (value.startsWith('color(srgb'))
          return [n[0] * 255, n[1] * 255, n[2] * 255, n[3] ?? 1]
        if (!value.startsWith('rgb')) throw new Error(`Unexpected ${value}`)
        return [n[0], n[1], n[2], n[3] ?? 1]
      }
      const luminance = ([r, g, b]: Color) => {
        const linear = (value: number) => {
          const unit = value / 255
          return unit <= 0.04045
            ? unit / 12.92
            : ((unit + 0.055) / 1.055) ** 2.4
        }
        return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)
      }
      const ratio = (a: Color, b: Color) => {
        const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x)
        return (high + 0.05) / (low + 0.05)
      }
      const over = (front: Color, back: Color): Color => [
        Math.round(front[0] * front[3] + back[0] * (1 - front[3])),
        Math.round(front[1] * front[3] + back[1] * (1 - front[3])),
        Math.round(front[2] * front[3] + back[2] * (1 - front[3])),
        1,
      ]
      const probe = document.createElement('div')
      document.body.append(probe)
      const root = document.documentElement
      const failures: string[] = []
      let checked = 0
      for (const look of looks)
        for (const scheme of ['light', 'dark'])
          for (const accent of accents) {
            root.dataset.look = look
            root.dataset.theme = scheme
            root.dataset.accent = accent
            const t: Record<string, Color> = {}
            for (const name of tokens) {
              probe.style.color = `var(--${name})`
              t[name] = parse(getComputedStyle(probe).color)
            }
            const chip = over(t['accent-soft'], t.surface)
            const tint = over(t['accent-tint'], t.bg)
            const pairs: [string, Color, Color, number][] = [
              ['text on bg', t.text, t.bg, 4.5],
              ['text on bg-deep', t.text, t['bg-deep'], 4.5],
              ['text on surface', t.text, t.surface, 4.5],
              ['text on surface-subtle', t.text, t['surface-subtle'], 4.5],
              ['text on surface-hover', t.text, t['surface-hover'], 4.5],
              ['secondary on bg', t['text-secondary'], t.bg, 4.5],
              ['secondary on bg-deep', t['text-secondary'], t['bg-deep'], 4.5],
              ['secondary on surface', t['text-secondary'], t.surface, 4.5],
              [
                'secondary on hover',
                t['text-secondary'],
                t['surface-hover'],
                4.5,
              ],
              ['muted on bg', t.muted, t.bg, 4.5],
              ['muted on bg-deep', t.muted, t['bg-deep'], 4.5],
              ['muted on surface', t.muted, t.surface, 4.5],
              ['muted on surface-subtle', t.muted, t['surface-subtle'], 4.5],
              ['muted on surface-hover', t.muted, t['surface-hover'], 4.5],
              ['muted on surface-sunken', t.muted, t['surface-sunken'], 4.5],
              ['accent on bg', t.accent, t.bg, 4.5],
              ['accent on bg-deep', t.accent, t['bg-deep'], 4.5],
              ['accent on surface', t.accent, t.surface, 4.5],
              ['accent on surface-subtle', t.accent, t['surface-subtle'], 4.5],
              ['accent on tinted card', t.accent, tint, 4.5],
              ['accent-hover on bg', t['accent-hover'], t.bg, 4.5],
              ['accent-strong on chip', t['accent-strong'], chip, 4.5],
              ['accent on chip', t.accent, chip, 4.5],
              ['button text', t['on-accent'], t['accent-fill'], 4.5],
              [
                'button text hover',
                t['on-accent'],
                t['accent-fill-hover'],
                4.5,
              ],
              ['success on bg', t['success-fg'], t.bg, 4.5],
              ['field border on surface', t['field-line'], t.surface, 3],
              [
                'field border on sunken',
                t['field-line'],
                t['surface-sunken'],
                3,
              ],
              ['accent line on bg', t.accent, t.bg, 3],
            ]
            for (const [name, front, back, minimum] of pairs) {
              checked++
              const value = ratio(front, back)
              if (value < minimum)
                failures.push(
                  `${look} ${scheme} ${accent}: ${name} ${value.toFixed(2)} < ${minimum}`,
                )
            }
          }
      probe.remove()
      return { checked, failures }
    },
    {
      looks: looks.map((item) => item.id),
      accents: accents.map((item) => item.id),
    },
  )
  expect(checked).toBe(looks.length * 2 * accents.length * 29)
  expect(failures).toEqual([])
})

for (const look of ['aurora', 'console'] as const) {
  test(`the ${look} look gives only the Shared lab badge its green treatment`, async ({
    page,
  }) => {
    await seedAppearance(page.context(), {
      mode: 'light',
      accent: 'foundry',
      look,
    })
    await openCreation(page)
    const preview = await page.context().newPage()
    await openCreation(preview, { preview: true })
    const read = (target: Page, scheme: string) =>
      target.evaluate((scheme) => {
        document.documentElement.dataset.theme = scheme
        const resolve = (name: string) => {
          const probe = document.createElement('i')
          probe.style.color = `var(--${name})`
          document.body.append(probe)
          const value = getComputedStyle(probe).color
          probe.remove()
          return value
        }
        const badge = document.querySelector('.environment-badge')!
        const style = getComputedStyle(badge)
        const dot = getComputedStyle(badge.querySelector('.status-dot')!)
        return {
          text: style.color,
          border: style.borderTopColor,
          dot: dot.backgroundColor,
          glow: dot.boxShadow,
          pulse: dot.animationName,
          muted: resolve('muted'),
          warning: resolve('warning-dot'),
          success: resolve('success-fg'),
          successDot: resolve('success-dot'),
          successLine: resolve('success-line'),
        }
      }, scheme)

    for (const scheme of ['light', 'dark']) {
      const shared = await read(page, scheme)
      expect(
        { text: shared.text, border: shared.border, dot: shared.dot },
        `${look} ${scheme}: Shared lab`,
      ).toEqual({
        text: shared.success,
        border: shared.successLine,
        dot: shared.successDot,
      })
      const local = await read(preview, scheme)
      expect(
        {
          text: local.text,
          dot: local.dot,
          glow: local.glow,
          pulse: local.pulse,
        },
        `${look} ${scheme}: Local preview`,
      ).toEqual({
        text: local.muted,
        dot: local.warning,
        glow: 'none',
        pulse: 'none',
      })
      expect(local.border, `${look} ${scheme}: Local preview border`).not.toBe(
        local.successLine,
      )
      if (look === 'aurora') {
        expect(shared.glow).not.toBe('none')
        expect(shared.pulse).toBe('look-pulse')
      }
    }
  })
}

test('the Console look keeps the phone tab strip as Classic has it and styles the wide sidebar buttons', async ({
  page,
}) => {
  await seedAppearance(page.context(), {
    mode: 'light',
    accent: 'foundry',
    look: 'console',
  })
  await openCreation(page)
  const phone = page.viewportSize()!.width <= 650
  const { classic, current, mono } = await page.evaluate(() => {
    const root = document.documentElement
    const first = document.querySelector('.chat-sidebar nav button')!
    const measure = (look: string) => {
      root.dataset.look = look
      const style = getComputedStyle(first)
      return {
        family: style.fontFamily,
        weight: style.fontWeight,
        size: style.fontSize,
        lineHeight: style.lineHeight,
        padding: style.padding,
        minHeight: style.minHeight,
        width: style.width,
        height: style.height,
      }
    }
    const classic = measure('classic')
    const current = measure('console')
    const probe = document.createElement('i')
    probe.style.fontFamily = 'var(--mono)'
    document.body.append(probe)
    const mono = getComputedStyle(probe).fontFamily
    probe.remove()
    return { classic, current, mono }
  })

  if (phone) expect(current).toEqual(classic)
  else
    expect(current).toMatchObject({
      family: mono,
      weight: '500',
      size: '12.5px',
      lineHeight: '17.5px',
      padding: '8px 12px',
      minHeight: '36px',
    })
})

test('template cards stay legible in dark mode for every accent', async ({
  page,
}, testInfo) => {
  await page.addInitScript((key) => {
    if (!localStorage.getItem(key))
      localStorage.setItem(
        key,
        JSON.stringify({ mode: 'dark', accent: 'foundry' }),
      )
  }, themeKey)
  await openCreation(page)
  const cards = page.locator('.creation-template')
  await expect(cards).toHaveCount(templates.length)
  await expect(
    page.locator('.creation-template[data-profile] .creation-chip-model'),
  ).toHaveText(templates.map((item) => `Model: ${item.model_profile.label}`))
  await expect(page.locator('.creation-template-check')).toHaveCount(0)
  for (const accent of ['foundry', 'orchid', 'lagoon']) {
    await page.evaluate(
      (value) => (document.documentElement.dataset.accent = value),
      accent,
    )
    for (const selector of [
      '.creation-template strong',
      '.creation-template-description',
      '.creation-chip',
    ]) {
      expect(
        await contrastAgainstBackground(page, selector),
        `${accent} ${selector}`,
      ).toBeGreaterThanOrEqual(4.5)
    }
  }
  await page.evaluate(
    () => (document.documentElement.dataset.accent = 'foundry'),
  )
  await cards.nth(1).click()
  await expect(cards.nth(1)).toHaveAttribute('aria-pressed', 'true')
  await expect(cards.nth(1).locator('.creation-template-check')).toBeVisible()
  await expect(page.locator('.creation-template-check')).toHaveCount(1)
  await page.evaluate(() => {
    document.querySelector('.creation-workspace')!.scrollTop = 0
    ;(document.activeElement as HTMLElement | null)?.blur()
  })
  await page.mouse.move(0, 0)
  await screenshot(page, testInfo, 'creation-start-dark.png')
})
