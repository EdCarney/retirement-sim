import type { MarketOverride, Schema } from '../../types'
import { InfoTip, NumberField, SelectField } from './Fields'

// One-line description per market.method, shown under the selector.
const METHOD_HINTS: Record<string, string> = {
  parametric: 'Correlated lognormal draws from the means/vols below.',
  student_t:
    'Same means/vols below, but fat-tailed Student-t shocks: crashes and booms are more extreme, and assets crash together.',
  bootstrap:
    'Resamples multi-year blocks of actual 1928+ US history (sequence risk included). The means/vols below are ignored; consider 25,000+ simulations.',
  all: 'Ensemble: runs the configured number of simulations through every model above and pools the results (3× the paths). The means/vols below apply to the parametric and student_t components.',
}

interface Props {
  market: MarketOverride | undefined
  schema: Schema
  onChange: (market: MarketOverride | undefined) => void
  feeDragBps: number | undefined
  onFeeChange: (bps: number | undefined) => void
}

// The config stores only *overrides* of the packaged defaults; fields here
// show the effective value and write an override only when it differs.
export function MarketForm({ market, schema, onChange, feeDragBps, onFeeChange }: Props) {
  const defaults = schema.market_defaults

  const method = market?.method ?? defaults.method
  const setMethod = (value: string) => {
    const next: MarketOverride = { ...market }
    if (value === defaults.method) delete next.method
    else next.method = value
    onChange(Object.keys(next).length === 0 ? undefined : next)
  }
  // The mean/vol table drives the parametric and student_t models only.
  const tableIgnored = method === 'bootstrap'

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
      <div className="field-row">
        <SelectField
          label="return model"
          value={method}
          options={schema.market_methods}
          onChange={setMethod}
          width={190}
        />
        {market?.method !== undefined && (
          <span style={{ color: 'var(--accent)', alignSelf: 'center' }} title="overrides the default">
            •
          </span>
        )}
      </div>
      <p className="hint">{METHOD_HINTS[method] ?? ''}</p>
      <p className="hint" style={{ opacity: tableIgnored ? 0.6 : 1 }}>
        Average annual return and volatility, nominal, per asset class. Values differing from the
        packaged defaults (marked •) are saved as overrides in this config's <code>market:</code>{' '}
        block; correlations and custom asset classes can be edited in the YAML directly.
      </p>
      <table className="mini" style={{ maxWidth: 420, opacity: tableIgnored ? 0.5 : 1 }}>
        <thead>
          <tr>
            <th>series</th>
            <th>
              mean
              <InfoTip text="Average annual return, nominal (before inflation). The center of the bell curve each year's return is drawn from." />
            </th>
            <th>
              vol
              <InfoTip text="Volatility — the standard deviation of annual returns. Higher vol means wider swings up and down, so more uncertainty in the outcome." />
            </th>
          </tr>
        </thead>
        <tbody>
          {schema.asset_classes.map(row)}
          {row('inflation')}
        </tbody>
      </table>
      <div className="field-row" style={{ marginTop: 14 }}>
        <NumberField
          label="fee drag"
          value={feeDragBps}
          onChange={onFeeChange}
          suffix="bps"
          min={0}
          placeholder="0"
          width={130}
          info="bps — basis points, hundredths of a percent (100 bps = 1%). The annual expense ratio skimmed from every account's return."
        />
      </div>
      <p className="hint" style={{ marginTop: 0 }}>
        Annual expense ratio applied to every account (100 bps = 1%/yr). Override it on an
        individual account with <code>fee_drag_bps</code> in the YAML.
      </p>
    </section>
  )
}
