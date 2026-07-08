// Chart palette. Recharts paints colors as SVG attributes from JS, so — unlike
// the DOM, which uses `var(--x)` directly — these must be resolved from the CSS
// custom properties in index.css at render time. `usePalette()` subscribes to
// the theme store so charts re-read (and recolor) the moment the theme flips.
//
// The single source of truth for every value below is index.css, which defines
// them per-theme. Keep the CLI's report.py palette aligned with the light theme
// so the web charts and the PNGs still read as the same product.
import { useTheme } from './theme'

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

// Ordered market scenarios, worst first: dimmer = worse, same hue. Labels and
// percentiles are theme-independent; only the color comes from a CSS token.
const SCENARIO_META: { percentile: number; label: string; token: string }[] = [
  { percentile: 10, label: 'significantly below average market (10th pct)', token: '--chart-scenario-10' },
  { percentile: 25, label: 'below average market (25th pct)', token: '--chart-scenario-25' },
  { percentile: 50, label: 'average market (50th pct)', token: '--chart-scenario-50' },
]

// The label/percentile list on its own, for consumers that don't need colors.
export const SCENARIOS = SCENARIO_META.map(({ percentile, label }) => ({ percentile, label }))

export interface Palette {
  bandOuter: string
  bandInner: string
  median: string
  failure: string
  grid: string
  baseline: string
  inkMuted: string
  hoverVeil: string
  scenarios: { percentile: number; label: string; color: string }[]
}

function readPalette(): Palette {
  return {
    bandOuter: cssVar('--chart-band-outer'),
    bandInner: cssVar('--chart-band-inner'),
    median: cssVar('--chart-median'),
    failure: cssVar('--chart-failure'),
    grid: cssVar('--grid'),
    baseline: cssVar('--baseline'),
    inkMuted: cssVar('--ink-muted'),
    hoverVeil: cssVar('--hover-veil'),
    scenarios: SCENARIO_META.map(({ percentile, label, token }) => ({
      percentile,
      label,
      color: cssVar(token),
    })),
  }
}

export function usePalette(): Palette {
  useTheme() // re-run (and re-read the CSS variables) when the theme changes
  return readPalette()
}
