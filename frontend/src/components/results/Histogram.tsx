import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { compactMoney } from '../../format'
import { usePalette } from '../../palette'
import type { HistogramData } from '../../types'

interface Props {
  histogram: HistogramData
  nSims: number
}

interface Bin {
  label: string
  range: string
  count: number
  depleted: boolean
}

function HistTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null
  const bin: Bin = payload[0].payload
  return (
    <div className="tooltip-box">
      <div className="tt-title">{bin.range}</div>
      <div className="tt-row">
        <span>paths</span>
        <strong>{bin.count.toLocaleString('en-US')}</strong>
      </div>
    </div>
  )
}

export function Histogram({ histogram, nSims }: Props) {
  const palette = usePalette()
  const { bin_edges, counts, n_failed, n_clipped, clip, median } = histogram
  const bins: Bin[] = counts.map((count, i) => ({
    label: compactMoney(bin_edges[i]),
    range: `${compactMoney(bin_edges[i])} – ${compactMoney(bin_edges[i + 1])}`,
    count,
    depleted: false,
  }))
  if (n_failed > 0) {
    bins.unshift({ label: 'depleted', range: 'portfolio depleted', count: n_failed, depleted: true })
  }
  // Category axis: label roughly every eighth bin to avoid clutter.
  const interval = Math.max(1, Math.floor(bins.length / 8))
  return (
    <>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={bins} margin={{ top: 8, right: 12, left: 8, bottom: 0 }} barCategoryGap={1}>
          <CartesianGrid vertical={false} stroke={palette.grid} />
          <XAxis
            dataKey="label"
            interval={interval}
            tick={{ fill: palette.inkMuted, fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: palette.baseline }}
          />
          <YAxis
            tick={{ fill: palette.inkMuted, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={50}
          />
          <Tooltip content={<HistTooltip />} cursor={{ fill: palette.hoverVeil }} />
          <Bar dataKey="count" isAnimationActive={false}>
            {bins.map((bin, i) => (
              <Cell key={i} fill={bin.depleted ? palette.failure : palette.median} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="chart-note">
        median {compactMoney(median)}
        {n_failed > 0 && (
          <>
            {' · '}
            <span style={{ color: palette.failure }}>
              {n_failed.toLocaleString('en-US')} of {nSims.toLocaleString('en-US')} paths depleted
              (red)
            </span>
          </>
        )}
        {n_clipped > 0 && <> · top 1% of paths (&gt; {compactMoney(clip)}) grouped in last bin</>}
      </div>
    </>
  )
}
