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

  // Streams NDJSON: progress lines drive `onProgress`, the final line is the
  // result. See /api/simulate in retirement_sim/web.py.
  simulate: async (
    config: RawConfig,
    nSims?: number,
    seed?: number,
    onProgress?: (fraction: number) => void,
  ): Promise<ResultsPayload> => {
    const response = await fetch(
      '/api/simulate',
      json({ config, n_sims: nSims ?? null, seed: seed ?? null }),
    )
    if (!response.ok || !response.body) {
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
}
