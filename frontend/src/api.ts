import type { MaxWithdrawal, RawConfig, ResultsPayload, Schema } from './types'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // non-JSON error body; keep the status text
    }
    throw new ApiError(response.status, detail)
  }
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

  simulate: (config: RawConfig, nSims?: number, seed?: number) =>
    request<ResultsPayload>(
      '/api/simulate',
      json({ config, n_sims: nSims ?? null, seed: seed ?? null }),
    ),

  maxWithdrawal: (config: RawConfig, nSims?: number, seed?: number) =>
    request<MaxWithdrawal | null>(
      '/api/max-withdrawal',
      json({ config, n_sims: nSims ?? null, seed: seed ?? null }),
    ),
}
