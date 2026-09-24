import { useEffect, useRef, useState } from 'react'
import { Monitor, Moon, Palette, Sun, type LucideIcon } from 'lucide-react'
import {
  accents,
  applyTheme,
  loadTheme,
  parseTheme,
  saveTheme,
  themeModes,
  themeStorageKey,
  type Theme,
  type ThemeMode,
} from './theme'

const modeIcons: Record<ThemeMode, LucideIcon> = {
  system: Monitor,
  light: Sun,
  dark: Moon,
}

export function ThemePicker() {
  const [theme, setTheme] = useState<Theme>(loadTheme)
  const summary = useRef<HTMLElement>(null)

  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key !== themeStorageKey) return
      const next = parseTheme(event.newValue)
      applyTheme(next)
      setTheme(next)
    }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [])

  const choose = (next: Theme) => {
    applyTheme(next)
    saveTheme(next)
    setTheme(next)
  }

  return (
    <details
      className="theme-menu"
      name="topbar-panel"
      onKeyDown={(event) => {
        if (event.key !== 'Escape' || !event.currentTarget.open) return
        event.currentTarget.open = false
        summary.current?.focus()
      }}
    >
      <summary
        ref={summary}
        className="chat-icon"
        title="Appearance"
        aria-label="Appearance"
      >
        <Palette size={17} aria-hidden="true" />
      </summary>
      <aside className="theme-panel" aria-label="Appearance settings">
        <fieldset>
          <legend>Theme</legend>
          <div className="theme-options">
            {themeModes.map((item) => {
              const Icon = modeIcons[item.id]
              return (
                <label key={item.id} className="theme-option">
                  <input
                    type="radio"
                    name="theme-mode"
                    value={item.id}
                    checked={theme.mode === item.id}
                    onChange={() => choose({ ...theme, mode: item.id })}
                  />
                  <Icon size={18} aria-hidden="true" />
                  {item.label}
                </label>
              )
            })}
          </div>
        </fieldset>
        <fieldset>
          <legend>Accent</legend>
          <div className="theme-options">
            {accents.map((item) => (
              <label key={item.id} className="theme-option">
                <input
                  type="radio"
                  name="theme-accent"
                  value={item.id}
                  checked={theme.accent === item.id}
                  onChange={() => choose({ ...theme, accent: item.id })}
                />
                <span
                  className={`theme-swatch theme-swatch-${item.id}`}
                  aria-hidden="true"
                />
                {item.label}
              </label>
            ))}
          </div>
        </fieldset>
        <p>Saved in this browser only.</p>
      </aside>
    </details>
  )
}
