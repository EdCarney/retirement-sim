// Shared chart palette — matches report.py so the web charts and the
// CLI's PNGs read as the same product.

export const BAND_OUTER = '#cde2fb' // 10th–90th percentile band
export const BAND_INNER = '#9ec5f4' // 25th–75th percentile band
export const MEDIAN = '#2a78d6'
export const FAILURE = '#d03b3b'
export const SURFACE = '#fcfcfb'
export const INK = '#0b0b0b'
export const INK_SECONDARY = '#52514e'
export const INK_MUTED = '#898781'
export const GRID = '#e1e0d9'
export const BASELINE = '#c3c2b7'

// Ordered market scenarios, worst first: lighter = worse, same hue.
export const SCENARIOS: { percentile: number; label: string; color: string }[] = [
  { percentile: 10, label: 'significantly below average market (10th pct)', color: '#86b6ef' },
  { percentile: 25, label: 'below average market (25th pct)', color: '#5598e7' },
  { percentile: 50, label: 'average market (50th pct)', color: '#2a78d6' },
]
