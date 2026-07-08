// Theme store. Dark is the default; the choice is persisted to localStorage.
// The active theme lives as a `data-theme` attribute on <html>, which the CSS
// variables in index.css key off of. Charts (which paint from JS, not CSS) read
// the resolved variables back out and subscribe here so they re-render on a flip.
import { useSyncExternalStore } from 'react'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'theme'
const DEFAULT: Theme = 'dark'

function stored(): Theme | null {
  const value = localStorage.getItem(STORAGE_KEY)
  return value === 'light' || value === 'dark' ? value : null
}

export function getTheme(): Theme {
  return (document.documentElement.dataset.theme as Theme) || DEFAULT
}

// Apply the persisted theme (or the default) to <html> before React mounts.
// index.html runs an inline copy of this pre-paint to avoid a flash; calling it
// again here is harmless and keeps the two in sync.
export function initTheme(): void {
  document.documentElement.dataset.theme = stored() ?? DEFAULT
}

const listeners = new Set<() => void>()

export function setTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
  localStorage.setItem(STORAGE_KEY, theme)
  listeners.forEach((notify) => notify())
}

export function toggleTheme(): void {
  setTheme(getTheme() === 'dark' ? 'light' : 'dark')
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange)
  return () => listeners.delete(onChange)
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, getTheme, () => DEFAULT)
}
