// Formatting helpers mirroring report.py's money() / _compact_money().

export function money(amount: number): string {
  return '$' + Math.round(amount).toLocaleString('en-US')
}

export function compactMoney(amount: number): string {
  const trim = (value: number) => {
    const text = value.toLocaleString('en-US', { maximumFractionDigits: 1 })
    return text.endsWith('.0') ? text.slice(0, -2) : text
  }
  const abs = Math.abs(amount)
  if (abs >= 1e9) return `$${trim(amount / 1e9)}B`
  if (abs >= 1e6) return `$${trim(amount / 1e6)}M`
  if (abs >= 1e3) return `$${trim(amount / 1e3)}K`
  return `$${amount.toFixed(0)}`
}

export function percent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`
}
