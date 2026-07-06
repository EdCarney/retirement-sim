import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { compactMoney, money } from '../../format'
import { BASELINE, GRID, INK_MUTED, SCENARIOS } from '../../palette'
import type { Bands, Marker } from '../../types'

interface Props {
  ages: number[]
  bands: Bands
  markers: Marker[]
}

function ScenarioTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  const datum = payload[0].payload
  return (
    <div className="tooltip-box">
      <div className="tt-title">Age {label}</div>
      {[...SCENARIOS].reverse().map(({ percentile, label: rowLabel }) => (
        <div key={percentile} className="tt-row">
          <span>{rowLabel}</span>
          <strong>{money(datum[`p${percentile}`])}</strong>
        </div>
      ))}
    </div>
  )
}

export function ScenarioChart({ ages, bands, markers }: Props) {
  const data = ages.map((age, i) => ({
    age,
    p10: bands.p10[i],
    p25: bands.p25[i],
    p50: bands.p50[i],
  }))
  return (
    <ResponsiveContainer width="100%" height={340}>
      <LineChart data={data} margin={{ top: 18, right: 12, left: 8, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis
          dataKey="age"
          type="number"
          domain={['dataMin', 'dataMax']}
          tickCount={10}
          tick={{ fill: INK_MUTED, fontSize: 11 }}
          tickLine={false}
          axisLine={{ stroke: BASELINE }}
        />
        <YAxis
          tickFormatter={compactMoney}
          tick={{ fill: INK_MUTED, fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          width={62}
        />
        <Tooltip content={<ScenarioTooltip />} />
        <Legend
          verticalAlign="top"
          align="left"
          iconType="plainline"
          wrapperStyle={{ fontSize: 12, paddingBottom: 8 }}
        />
        {[...SCENARIOS].reverse().map(({ percentile, label, color }) => (
          <Line
            key={percentile}
            dataKey={`p${percentile}`}
            name={label}
            stroke={color}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        ))}
        {markers.map((marker) => (
          <ReferenceLine
            key={marker.label}
            x={marker.age}
            stroke={BASELINE}
            label={{ value: marker.label, position: 'top', fill: INK_MUTED, fontSize: 10 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
