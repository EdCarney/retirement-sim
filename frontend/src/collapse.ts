// Per-section collapse state for the editor cards. This is a viewing
// preference, not plan data, so it lives in localStorage (like the theme) —
// keyed globally by section id, not per config, so a section you rarely edit
// stays collapsed across every config.
import { useState } from 'react'

const KEY = 'collapsedSections'

function readAll(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '{}')
  } catch {
    return {}
  }
}

function persist(id: string, collapsed: boolean): void {
  const all = readAll()
  all[id] = collapsed
  localStorage.setItem(KEY, JSON.stringify(all))
}

export function useCollapsed(id: string): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState(() => readAll()[id] ?? false)
  const toggle = () =>
    setCollapsed((prev) => {
      const next = !prev
      persist(id, next)
      return next
    })
  return [collapsed, toggle]
}
