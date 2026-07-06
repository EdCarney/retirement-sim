import type { MarketOverride, Schema } from '../../types'
import { NumberField } from './Fields'

interface Props {
  market: MarketOverride | undefined
  schema: Schema
  onChange: (market: MarketOverride | undefined) => void
}

// The config stores only *overrides* of the packaged defaults; fields here
// show the effective value and write an override only when it differs.
export function MarketForm({ market, schema, onChange }: Props) {
  const defaults = schema.market_defaults

  const effective = (series: string, field: 'mean' | 'vol'): number => {
    const override =
      series === 'inflation' ? market?.inflation?.[field] : market?.asset_classes?.[series]?.[field]
    const fallback =
      series === 'inflation' ? defaults.inflation[field] : defaults.asset_classes[series]?.[field]
    return override ?? fallback
  }

  const setValue = (series: string, field: 'mean' | 'vol', value: number | undefined) => {
    const fallback =
      series === 'inflation' ? defaults.inflation[field] : defaults.asset_classes[series]?.[field]
    const next: MarketOverride = {
      ...market,
      asset_classes: { ...market?.asset_classes },
      inflation: { ...market?.inflation },
    }
    const isDefault = value === undefined || Math.abs(value - fallback) < 1e-12
    if (series === 'inflation') {
      if (isDefault) delete next.inflation![field]
      else next.inflation![field] = value
    } else {
      const series_override = { ...next.asset_classes![series] }
      if (isDefault) delete series_override[field]
      else series_override[field] = value
      if (Object.keys(series_override).length === 0) delete next.asset_classes![series]
      else next.asset_classes![series] = series_override
    }
    // Prune empty blocks so untouched configs keep no market: section.
    if (Object.keys(next.inflation!).length === 0) delete next.inflation
    if (Object.keys(next.asset_classes!).length === 0) delete next.asset_classes
    onChange(Object.keys(next).length === 0 ? undefined : next)
  }

  const isOverridden = (series: string, field: 'mean' | 'vol') =>
    (series === 'inflation'
      ? market?.inflation?.[field]
      : market?.asset_classes?.[series]?.[field]) !== undefined

  const row = (series: string) => (
    <tr key={series}>
      <td>
        {series}
        {(isOverridden(series, 'mean') || isOverridden(series, 'vol')) && (
          <span style={{ color: 'var(--accent)' }} title="overrides the default"> •</span>
        )}
      </td>
      <td>
        <NumberField value={effective(series, 'mean')} onChange={(v) => setValue(series, 'mean', v)} percent width={110} />
      </td>
      <td>
        <NumberField value={effective(series, 'vol')} onChange={(v) => setValue(series, 'vol', v)} percent width={110} />
      </td>
    </tr>
  )

  return (
    <section className="card">
      <h3>Market assumptions</h3>
      <p className="hint">
        Average annual return and volatility, nominal, per asset class. Values differing from the
        packaged defaults (marked •) are saved as overrides in this config's <code>market:</code>{' '}
        block; correlations and custom asset classes can be edited in the YAML directly.
      </p>
      <table className="mini" style={{ maxWidth: 420 }}>
        <thead>
          <tr>
            <th>series</th>
            <th>mean</th>
            <th>vol</th>
          </tr>
        </thead>
        <tbody>
          {schema.asset_classes.map(row)}
          {row('inflation')}
        </tbody>
      </table>
    </section>
  )
}
