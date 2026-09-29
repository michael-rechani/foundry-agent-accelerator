export const underTheHoodKey = 'ai-foundry-lab-under-the-hood'

// Views that only make sense with technical details on.
export const hoodViews = ['performance', 'log'] as const

export function loadUnderTheHood(): boolean {
  try {
    return localStorage.getItem(underTheHoodKey) === '1'
  } catch {
    return false
  }
}

export function saveUnderTheHood(on: boolean) {
  try {
    localStorage.setItem(underTheHoodKey, on ? '1' : '0')
  } catch {
    // Storage can be unavailable; the choice still applies until reload.
  }
}
