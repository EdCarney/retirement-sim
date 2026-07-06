import type { ConfigFile, ConfigListEntry, RawConfig, ResultsPayload, Schema } from './types'

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
  listConfigs: () => request<ConfigListEntry[]>('/api/configs'),

  getConfig: (name: string) => request<ConfigFile>(`/api/configs/${encodeURIComponent(name)}`),

  saveConfig: (name: string, config: RawConfig) =>
    request<{ name: string; yaml: string }>(`/api/configs/${encodeURIComponent(name)}`, {
      ...json(config),
      method: 'PUT',
    }),

  createConfig: (name: string, copyFrom?: string) =>
    request<ConfigFile>(
      `/api/configs/${encodeURIComponent(name)}` +
        (copyFrom ? `?copy_from=${encodeURIComponent(copyFrom)}` : ''),
      { method: 'POST' },
    ),

  deleteConfig: (name: string) =>
    request<{ deleted: string }>(`/api/configs/${encodeURIComponent(name)}`, { method: 'DELETE' }),

  validate: (config: RawConfig) =>
    request<{ valid: boolean; error: string | null }>('/api/validate', json(config)),

  schema: () => request<Schema>('/api/schema'),

  simulate: (config: RawConfig, nSims?: number, seed?: number) =>
    request<ResultsPayload>(
      '/api/simulate',
      json({ config, n_sims: nSims ?? null, seed: seed ?? null }),
    ),
}
