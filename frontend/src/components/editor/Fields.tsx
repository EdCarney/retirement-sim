// Shared form field primitives. Rate-like values (allocations, increases,
// market means/vols) are DISPLAYED as percentages but STORED as decimals,
// matching the YAML schema.

import { useLayoutEffect, useRef, useState } from 'react'
import type { ChangeEvent, CSSProperties } from 'react'

interface NumberFieldProps {
  label?: string
  value: number | undefined
  onChange: (value: number | undefined) => void
  percent?: boolean
  /** Render as a whole-number field with live thousands separators (e.g. 130,000). */
  group?: boolean
  suffix?: string
  step?: number
  min?: number
  placeholder?: string
  width?: number
  /** Optional glossary text; shows an ⓘ tooltip next to the label. */
  info?: string
}

// A small ⓘ affordance that reveals a definition on hover or keyboard focus.
// Used to gloss jargon (PIA, FRA, COLA, bps, vol …) inline with the field it
// labels, so the meaning is one hover away without cluttering the form.
export function InfoTip({ text }: { text: string }) {
  return (
    <span className="infotip">
      <span className="infotip-icon" tabIndex={0} role="img" aria-label={text}>
        i
      </span>
      <span className="infotip-bubble" role="tooltip">
        {text}
      </span>
    </span>
  )
}

// Field label with an optional trailing info tooltip. Renders nothing when
// there is no label, matching the previous `{label && <label>…}` behavior.
function FieldLabel({ label, info }: { label?: string; info?: string }) {
  if (!label) return null
  return (
    <label>
      {label}
      {info && <InfoTip text={info} />}
    </label>
  )
}

function toDisplay(value: number | undefined, percent: boolean): string {
  if (value === undefined || Number.isNaN(value)) return ''
  if (!percent) return String(value)
  // Trim float noise from the ×100 (0.02 * 100 === 2.0000000000000004).
  return String(parseFloat((value * 100).toPrecision(12)))
}

// Insert commas every three digits (integers only).
function groupDigits(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

// A whole-number input that shows thousands separators as you type. Native
// number inputs can't render commas, so this is a text input that strips
// non-digits on every keystroke and re-groups, restoring the caret to the same
// logical position (counted in digits) so inserted commas don't shift it.
function GroupedInput({
  value,
  onChange,
  placeholder,
  style,
}: {
  value: number | undefined
  onChange: (value: number | undefined) => void
  placeholder?: string
  style?: CSSProperties
}) {
  const ref = useRef<HTMLInputElement>(null)
  const caret = useRef<number | null>(null)

  useLayoutEffect(() => {
    if (caret.current !== null && ref.current) {
      ref.current.setSelectionRange(caret.current, caret.current)
      caret.current = null
    }
  })

  const display = value === undefined || Number.isNaN(value) ? '' : groupDigits(String(Math.round(value)))

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value
    const pos = e.target.selectionStart ?? raw.length
    const digitsBeforeCaret = raw.slice(0, pos).replace(/\D/g, '').length
    const digits = raw.replace(/\D/g, '')

    if (digits === '') {
      onChange(undefined)
      caret.current = 0
      return
    }
    onChange(Number(digits))

    // Walk the regrouped string to the caret's digit index, skipping commas.
    const grouped = groupDigits(String(Number(digits)))
    let seen = 0
    let i = 0
    for (; i < grouped.length && seen < digitsBeforeCaret; i++) {
      if (grouped[i] >= '0' && grouped[i] <= '9') seen++
    }
    caret.current = i
  }

  return (
    <input
      ref={ref}
      type="text"
      inputMode="numeric"
      value={display}
      placeholder={placeholder}
      style={style}
      onChange={handleChange}
    />
  )
}

// A native number input backed by a local editing draft. While the user is
// typing (focused), the field shows exactly what they typed — including an
// empty field or a trailing "." — rather than the value derived from the
// prop. Without this, a parent that rewrites the value on an empty field
// (e.g. MarketForm falling back to the default when an override is cleared)
// would snap the field back mid-edit. On blur the draft is dropped so the
// field re-syncs with the canonical value.
function PlainNumberInput({
  value,
  onChange,
  percent,
  step,
  min,
  placeholder,
  style,
}: {
  value: number | undefined
  onChange: (value: number | undefined) => void
  percent: boolean
  step?: number
  min?: number
  placeholder?: string
  style?: CSSProperties
}) {
  const [draft, setDraft] = useState<string | null>(null)
  const display = draft !== null ? draft : toDisplay(value, percent)

  return (
    <input
      type="number"
      value={display}
      step={step ?? (percent ? 0.1 : undefined)}
      min={min}
      placeholder={placeholder}
      style={style}
      onChange={(e) => {
        const text = e.target.value
        setDraft(text)
        if (text === '') {
          onChange(undefined)
        } else {
          const parsed = Number(text)
          if (Number.isNaN(parsed)) return
          onChange(percent ? parseFloat((parsed / 100).toPrecision(12)) : parsed)
        }
      }}
      onBlur={() => setDraft(null)}
    />
  )
}

export function NumberField({
  label,
  value,
  onChange,
  percent = false,
  group = false,
  suffix,
  step,
  min,
  placeholder,
  width,
  info,
}: NumberFieldProps) {
  const sfx = suffix ?? (percent ? '%' : undefined)
  // Leave room on the right for the unit label, scaled to its length.
  const inputStyle: CSSProperties | undefined = sfx
    ? { paddingRight: 14 + sfx.length * 7 }
    : undefined

  const input = group ? (
    <GroupedInput value={value} onChange={onChange} placeholder={placeholder} style={inputStyle} />
  ) : (
    <PlainNumberInput
      value={value}
      onChange={onChange}
      percent={percent}
      step={step}
      min={min}
      placeholder={placeholder}
      style={inputStyle}
    />
  )
  return (
    <div className="field" style={width ? { width, minWidth: width } : undefined}>
      <FieldLabel label={label} info={info} />
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
  info?: string
}

export function SelectField({ label, value, options, onChange, width, info }: SelectFieldProps) {
  const known = options.includes(value) ? options : [value, ...options]
  return (
    <div className="field" style={width ? { width, minWidth: width } : undefined}>
      <FieldLabel label={label} info={info} />
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
  info?: string
}

export function CheckField({ label, checked, onChange, info }: CheckFieldProps) {
  return (
    <div className="field checkbox">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <label>
        {label}
        {info && <InfoTip text={info} />}
      </label>
    </div>
  )
}
