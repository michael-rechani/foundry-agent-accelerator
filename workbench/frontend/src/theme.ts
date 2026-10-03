export const themeStorageKey = 'ai-foundry-lab-theme'

export const themeModes = [
  { id: 'system', label: 'System' },
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
] as const

export const accents = [
  { id: 'foundry', label: 'Foundry' },
  { id: 'orchid', label: 'Orchid' },
  { id: 'lagoon', label: 'Lagoon' },
] as const

export const looks = [
  { id: 'classic', label: 'Classic' },
  { id: 'aurora', label: 'Aurora' },
  { id: 'console', label: 'Console' },
] as const

export type ThemeMode = (typeof themeModes)[number]['id']
export type Accent = (typeof accents)[number]['id']
export type Look = (typeof looks)[number]['id']
export type Theme = { mode: ThemeMode; accent: Accent; look: Look }

export const defaultTheme: Theme = {
  mode: 'system',
  accent: 'foundry',
  look: 'classic',
}

export function parseTheme(value: string | null): Theme {
  try {
    const data: unknown = JSON.parse(value ?? '')
    if (typeof data !== 'object' || data === null) return defaultTheme
    const { mode, accent, look } = data as Record<string, unknown>
    return {
      mode: themeModes.some((item) => item.id === mode)
        ? (mode as ThemeMode)
        : defaultTheme.mode,
      accent: accents.some((item) => item.id === accent)
        ? (accent as Accent)
        : defaultTheme.accent,
      look: looks.some((item) => item.id === look)
        ? (look as Look)
        : defaultTheme.look,
    }
  } catch {
    return defaultTheme
  }
}

export function loadTheme(): Theme {
  try {
    return parseTheme(localStorage.getItem(themeStorageKey))
  } catch {
    return defaultTheme
  }
}

export function saveTheme(theme: Theme) {
  try {
    localStorage.setItem(themeStorageKey, JSON.stringify(theme))
  } catch {
    // Storage can be unavailable; the choice still applies until reload.
  }
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme.mode
  document.documentElement.dataset.accent = theme.accent
  document.documentElement.dataset.look = theme.look
}
