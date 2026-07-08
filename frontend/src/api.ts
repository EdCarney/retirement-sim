import type { MaxWithdrawal, Plan, RawConfig, ResultsPayload, Schema, User } from './types'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// Registered by App: called when a request to a protected endpoint 401s, so a
// session that expires mid-use bounces the user back to the login screen. The
// auth endpoints (/api/auth/*) are exempt — a failed login is handled locally
// by the login screen, and the initial /api/auth/me probe drives the gate itself.
let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler
}

function handleUnauthorized(url: string, status: number): void {
  if (status === 401 && !url.startsWith('/api/auth/')) onUnauthorized?.()
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  // Send the session cookie with every call (same-origin in prod and via the
  // Vite dev proxy, so this is same-origin either way).
  const response = await fetch(url, { credentials: 'same-origin', ...init })
  if (!response.ok) {
    handleUnauthorized(url, response.status)
    let detail = response.statusText
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // non-JSON error body; keep the status text
    }
    throw new ApiError(response.status, detail)
  }
  // 204 No Content (e.g. DELETE) has no body to parse.
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  // Canonical YAML for download — the single writer that keeps files
  // CLI-byte-matched (see /api/serialize in retirement_sim/web.py).
  serialize: (config: RawConfig) =>
    request<{ yaml: string }>('/api/serialize', json(config)).then((r) => r.yaml),

  validate: (config: RawConfig) =>
    request<{ valid: boolean; error: string | null }>('/api/validate', json(config)),

  schema: () => request<Schema>('/api/schema'),

  // Streams NDJSON: progress lines drive `onProgress`, the final line is the
  // result. See /api/simulate in retirement_sim/web.py.
  simulate: async (
    config: RawConfig,
    nSims?: number,
    seed?: number,
    onProgress?: (fraction: number) => void,
  ): Promise<ResultsPayload> => {
    const response = await fetch('/api/simulate', {
      credentials: 'same-origin',
      ...json({ config, n_sims: nSims ?? null, seed: seed ?? null }),
    })
    if (!response.ok || !response.body) {
      handleUnauthorized('/api/simulate', response.status)
      // An invalid config short-circuits to 422 before the stream opens.
      let detail = response.statusText
      try {
        const body = await response.json()
        if (typeof body.detail === 'string') detail = body.detail
      } catch {
        // non-JSON error body; keep the status text
      }
      throw new ApiError(response.status, detail)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let result: ResultsPayload | null = null
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let nl: number
      while ((nl = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, nl).trim()
        buffer = buffer.slice(nl + 1)
        if (!line) continue
        const msg = JSON.parse(line)
        if (msg.type === 'progress') onProgress?.(msg.value as number)
        else if (msg.type === 'result') result = msg.payload as ResultsPayload
        else if (msg.type === 'error') throw new ApiError(500, msg.error as string)
      }
    }
    if (!result) throw new ApiError(500, 'simulation returned no result')
    return result
  },

  maxWithdrawal: (config: RawConfig, nSims?: number, seed?: number) =>
    request<MaxWithdrawal | null>(
      '/api/max-withdrawal',
      json({ config, n_sims: nSims ?? null, seed: seed ?? null }),
    ),

  // ── auth ──────────────────────────────────────────────────────────────────

  // Whether the login screen should offer a signup tab.
  authConfig: () => request<{ signup_enabled: boolean }>('/api/auth/config'),

  // Current session's user, or throws ApiError(401) if not logged in.
  me: () => request<{ user: User }>('/api/auth/me').then((r) => r.user),

  login: (username: string, password: string) =>
    request<{ user: User }>('/api/auth/login', json({ username, password })).then(
      (r) => r.user,
    ),

  signup: (username: string, password: string, inviteCode: string) =>
    request<{ user: User }>(
      '/api/auth/signup',
      json({ username, password, invite_code: inviteCode }),
    ).then((r) => r.user),

  logout: () => request<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),

  // ── per-user plan storage ─────────────────────────────────────────────────

  listPlans: () => request<Plan[]>('/api/plans'),

  createPlan: (plan: Plan) => request<Plan>('/api/plans', json(plan)),

  updatePlan: (id: string, body: { name: string; config: RawConfig }) =>
    request<Plan>(`/api/plans/${encodeURIComponent(id)}`, {
      ...json(body),
      method: 'PUT',
    }),

  deletePlan: (id: string) =>
    request<void>(`/api/plans/${encodeURIComponent(id)}`, { method: 'DELETE' }),
}
