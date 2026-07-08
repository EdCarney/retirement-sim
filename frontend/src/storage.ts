// Browser-owned plan storage.
//
// The server holds no plan state (see retirement_sim/web.py): this module is
// the source of truth for "which plans exist". Plans live in React state and
// are mirrored to localStorage so work survives a reload. Nothing here talks
// to the backend.

import { dump, load } from 'js-yaml'
import type { Plan, RawConfig } from './types'

const PLANS_KEY = 'retirement-sim.plans'
const SELECTED_KEY = 'retirement-sim.selected'

// Reject anything much larger than a real plan so a huge/malformed upload
// can't wedge the tab parsing it.
export const MAX_UPLOAD_BYTES = 1_000_000

// Starter plan for "new"; must pass build_config on the backend.
export function templateConfig(): RawConfig {
  return {
    person: { current_age: 35, retirement_age: 65, death_age: 95 },
    accounts: [
      {
        name: 'retirement',
        type: '401k',
        balance: 100_000,
        allocation: { stocks: 0.8, bonds: 0.2 },
      },
    ],
    contributions: [
      { account: 'retirement', annual_amount: 10_000, index_to_inflation: true },
    ],
    goal: { type: 'retirement_income', monthly_income_today: 5_000 },
    simulation: { n_sims: 10_000 },
    output: { dir: 'output', charts: true, chart_dollars: 'real' },
  }
}

export function newId(): string {
  return crypto.randomUUID()
}

export function loadPlans(): Plan[] {
  try {
    const raw = localStorage.getItem(PLANS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (p): p is Plan => p && typeof p.id === 'string' && typeof p.name === 'string' && !!p.config,
    )
  } catch {
    return []
  }
}

export function loadSelected(): string | null {
  return localStorage.getItem(SELECTED_KEY)
}

export function savePlans(plans: Plan[], selected: string | null): void {
  try {
    localStorage.setItem(PLANS_KEY, JSON.stringify(plans))
    if (selected) localStorage.setItem(SELECTED_KEY, selected)
    else localStorage.removeItem(SELECTED_KEY)
  } catch {
    // Storage full or unavailable (e.g. private mode): keep working in memory.
  }
}

// Parse an uploaded YAML file into a plan config. Throws a user-facing Error
// on oversized input or unparseable / non-mapping YAML. Schema validity is
// left to the backend /api/validate call.
export async function parseUpload(file: File): Promise<RawConfig> {
  if (file.size > MAX_UPLOAD_BYTES) {
    throw new Error(`file too large (${Math.round(file.size / 1024)} KB; max 1 MB)`)
  }
  const text = await file.text()
  let parsed: unknown
  try {
    parsed = load(text)
  } catch (error) {
    throw new Error(`could not parse YAML: ${error instanceof Error ? error.message : error}`)
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('YAML must be a mapping (a plan config)')
  }
  return parsed as RawConfig
}

// Trigger a browser download of `text` as `filename`.
export function downloadFile(filename: string, text: string): void {
  const blob = new Blob([text], { type: 'application/x-yaml' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// Local (offline) fallback serializer, used only if /api/serialize is
// unreachable. The backend endpoint is canonical and CLI-byte-matched.
export function localSerialize(config: RawConfig): string {
  return dump(config, { sortKeys: false, noRefs: true })
}
