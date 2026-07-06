// Shared form field primitives. Rate-like values (allocations, increases,
// market means/vols) are DISPLAYED as percentages but STORED as decimals,
// matching the YAML schema.

interface NumberFieldProps {
  label?: string
  value: number | undefined
  onChange: (value: number | undefined) => void
  percent?: boolean
  suffix?: string
  step?: number
  min?: number
  placeholder?: string
  width?: number
}

function toDisplay(value: number | undefined, percent: boolean): string {
  if (value === undefined || Number.isNaN(value)) return ''
  if (!percent) return String(value)
  // Trim float noise from the ×100 (0.02 * 100 === 2.0000000000000004).
  return String(parseFloat((value * 100).toPrecision(12)))
}

export function NumberField({
  label,
  value,
  onChange,
  percent = false,
  suffix,
  step,
  min,
  placeholder,
  width,
}: NumberFieldProps) {
  const input = (
    <input
      type="number"
      value={toDisplay(value, percent)}
      step={step ?? (percent ? 0.1 : undefined)}
      min={min}
      placeholder={placeholder}
      onChange={(e) => {
        if (e.target.value === '') {
          onChange(undefined)
        } else {
          const parsed = Number(e.target.value)
          onChange(percent ? parseFloat((parsed / 100).toPrecision(12)) : parsed)
        }
      }}
    />
  )
  const sfx = suffix ?? (percent ? '%' : undefined)
  return (
    <div className="field" style={width ? { width, minWidth: width } : undefined}>
      {label && <label>{label}</label>}
      {sfx ? (
        <span className="suffix-wrap">
          {input}
          <span className="suffix">{sfx}</span>
        </span>
      ) : (
        input
      )}
    </div>
  )
}

interface TextFieldProps {
  label?: string
  value: string
  onChange: (value: string) => void
  width?: number
}

export function TextField({ label, value, onChange, width }: TextFieldProps) {
  return (
    <div className="field" style={width ? { width, minWidth: width } : undefined}>
      {label && <label>{label}</label>}
      <input type="text" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}

interface SelectFieldProps {
  label?: string
  value: string
  options: string[]
  onChange: (value: string) => void
  width?: number
}

export function SelectField({ label, value, options, onChange, width }: SelectFieldProps) {
  const known = options.includes(value) ? options : [value, ...options]
  return (
    <div className="field" style={width ? { width, minWidth: width } : undefined}>
      {label && <label>{label}</label>}
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {known.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  )
}

interface CheckFieldProps {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
}

export function CheckField({ label, checked, onChange }: CheckFieldProps) {
  return (
    <div className="field checkbox">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <label>{label}</label>
    </div>
  )
}
