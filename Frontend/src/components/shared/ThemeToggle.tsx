// Light/dark theme toggle. Flips document.documentElement[data-theme] and
// persists the choice in sessionStorage (per policy: not localStorage).
// Light is the default. The dark palette lives under [data-theme="dark"] in
// global.css, so flipping the attribute re-themes the whole app.

import { useEffect, useState, type JSX } from 'react'
import { SunIcon, MoonIcon } from '@/components/shared/icons'

type Theme = 'light' | 'dark'
const STORAGE_KEY = 'theme'

export function getStoredTheme(): Theme {
  return sessionStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light'
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme)
}

export function ThemeToggle(): JSX.Element {
  const [theme, setTheme] = useState<Theme>(getStoredTheme)

  useEffect(() => {
    applyTheme(theme)
    sessionStorage.setItem(STORAGE_KEY, theme)
  }, [theme])

  const toggle = (): void => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))

  return (
    <button
      type="button"
      className="btn-icon"
      aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
      title={theme === 'dark' ? 'Light theme' : 'Dark theme'}
      aria-pressed={theme === 'dark'}
      onClick={toggle}
    >
      {theme === 'dark' ? <SunIcon size={18} /> : <MoonIcon size={18} />}
    </button>
  )
}
