// TypeScript mirror of the YAML config schema (retirement_sim/config.py)
// and the /api/simulate results payload (retirement_sim/web.py).

export interface Person {
  current_age: number
  retirement_age: number
  death_age: number
}

export interface GlidePoint {
  age: number
  allocation: Record<string, number>
}

export interface Account {
  name: string
  type: string
  balance: number
  allocation?: Record<string, number>
  glide_path?: GlidePoint[]
  fee_drag_bps?: number
}

export interface ContributionChange {
  age: number
  annual_amount?: number
  // Salary mode (YAML/CLI): contribute `savings_rate` of `salary` instead.
  salary?: number
  savings_rate?: number
  index_to_inflation?: boolean
  extra_annual_increase?: number
}

export interface Contribution {
  account: string
  annual_amount?: number
  // Salary mode (YAML/CLI): contribute `savings_rate` of `salary` instead.
  salary?: number
  savings_rate?: number
  index_to_inflation?: boolean
  extra_annual_increase?: number
  changes?: ContributionChange[]
}

export interface Goal {
  type: string
  monthly_income_today?: number
  amount?: number
  basis?: string
}

export interface SocialSecurity {
  monthly_benefit_today?: number
  claiming_age: number
  // PIA mode (YAML/CLI): derive the benefit from your full-retirement-age
  // amount, applying SSA claiming-age factors.
  pia_monthly?: number
  full_retirement_age?: number
  // When false, the values are retained but the plan runs as if there were no
  // Social Security. Omitted (defaults true) when enabled, to keep YAML clean.
  enabled?: boolean
}

export interface SeriesParams {
  mean: number
  vol: number
}

export interface MarketOverride {
  method?: string
  student_t?: { df?: number }
  bootstrap?: { block_years?: number; data?: string; recenter?: boolean }
  asset_classes?: Record<string, Partial<SeriesParams>>
  inflation?: Partial<SeriesParams>
  correlations?: Record<string, number>
}

export interface RawConfig {
  person: Person
  accounts: Account[]
  contributions?: Contribution[]
  goal: Goal
  social_security?: SocialSecurity
  market?: MarketOverride
  fees?: { drag_bps?: number }
  simulation?: { n_sims?: number; seed?: number | null }
  output?: Record<string, unknown>
}

// --- API shapes ---

export interface ConfigListEntry {
  name: string
  modified: string
  goal_type: string | null
  error: string | null
}

export interface ConfigFile {
  name: string
  config: RawConfig
  yaml: string
  error: string | null
}

export interface Schema {
  account_types: string[]
  goal_types: string[]
  goal_bases: string[]
  chart_dollars: string[]
  asset_classes: string[]
  market_methods: string[]
  market_defaults: {
    method: string
    student_t: { df: number }
    bootstrap: { block_years: number; recenter: boolean }
    asset_classes: Record<string, SeriesParams>
    inflation: SeriesParams
    correlations: Record<string, number>
  }
}

export type Basis = 'real' | 'nominal'

export type Bands = Record<string, number[]> // p10 ... p90, one value per age

export interface TableRow {
  percentile: number
  real: number
  nominal: number
}

export interface ResultsTable {
  title: string
  age: number
  rows: TableRow[]
}

export interface HistogramData {
  bin_edges: number[]
  counts: number[]
  n_failed: number
  n_clipped: number
  clip: number
  median: number
}

export interface Marker {
  age: number
  label: string
}

export interface Assumption {
  series: string
  mean: number
  vol: number
}

export interface ResultsPayload {
  goal: { type: string; text: string }
  n_sims: number
  seed: number | null
  success_probability: number
  score: { label: string; severity: 'ok' | 'warn' | 'bad' }
  confidence: { level: number; percentile: number; age: number; real: number; nominal: number }
  failed_paths: number
  median_depletion_age: number | null
  starting_balance: number
  ages: number[]
  percentiles: number[]
  bands: Record<Basis, Bands>
  markers: Marker[]
  tables: ResultsTable[]
  histogram: { at: string; age: number } & Record<Basis, HistogramData>
  assumptions: Assumption[]
}
