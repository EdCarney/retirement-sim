import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { compactMoney, money } from '../../format'
import { usePalette } from '../../palette'
import type { Bands, Marker } from '../../types'

interface Props {
  ages: number[]
  bands: Bands
  markers: Marker[]
}

const ROWS: { key: string; label: string }[] = [
  { key: 'p90', label: '90th percentile' },
  { key: 'p75', label: '75th percentile' },
  { key: 'p50', label: 'median' },
  { key: 'p25', label: '25th percentile' },
  { key: 'p10', label: '10th percentile' },
]

function FanTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  const datum = payload[0].payload
  return (
    <div className="tooltip-box">
      <div className="tt-title">Age {label}</div>
      {ROWS.map(({ key, label: rowLabel }) => (
        <div key={key} className="tt-row">
          <span>{rowLabel}</span>
          <strong>{money(datum[key])}</strong>
        </div>
      ))}
    </div>
  )
}

export function FanChart({ ages, bands, markers }: Props) {
  const palette = usePalette()
  const data = ages.map((age, i) => ({
    age,
    p10: bands.p10[i],
    p25: bands.p25[i],
    p50: bands.p50[i],
    p75: bands.p75[i],
    p90: bands.p90[i],
    outer: [bands.p10[i], bands.p90[i]],
    inner: [bands.p25[i], bands.p75[i]],
  }))
  return (
    <ResponsiveContainer width="100%" height={340}>
      <ComposedChart data={data} margin={{ top: 18, right: 12, left: 8, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={palette.grid} />
        <XAxis
          dataKey="age"
          type="number"
          domain={['dataMin', 'dataMax']}
          tickCount={10}
          tick={{ fill: palette.inkMuted, fontSize: 11 }}
          tickLine={false}
          axisLine={{ stroke: palette.baseline }}
        />
        <YAxis
          tickFormatter={compactMoney}
          tick={{ fill: palette.inkMuted, fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          width={62}
        />
        <Tooltip content={<FanTooltip />} />
        <Area dataKey="outer" stroke="none" fill={palette.bandOuter} fillOpacity={1} isAnimationActive={false} />
        <Area dataKey="inner" stroke="none" fill={palette.bandInner} fillOpacity={1} isAnimationActive={false} />
        <Line dataKey="p50" stroke={palette.median} strokeWidth={2} dot={false} isAnimationActive={false} />
        {markers.map((marker) => (
          <ReferenceLine
            key={marker.label}
            x={marker.age}
            stroke={palette.baseline}
            label={{ value: marker.label, position: 'top', fill: palette.inkMuted, fontSize: 10 }}
          />
        ))}
      </ComposedChart>
    </ResponsiveContainer>
  )
}
