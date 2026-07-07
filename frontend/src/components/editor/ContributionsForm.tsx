import { money } from '../../format'
import type { Contribution, ContributionChange } from '../../types'
import { CheckField, NumberField, SelectField } from './Fields'

interface Props {
  contributions: Contribution[]
  accountNames: string[]
  onChange: (contributions: Contribution[]) => void
}

const INDEX_INFO =
  "When on, the contribution grows with each path's simulated inflation, so it keeps constant buying power. When off, it stays a fixed nominal dollar amount every year."
const EXTRA_INCREASE_INFO =
  'A real raise on top of inflation — e.g. 2% models a contribution that outpaces inflation by 2%/yr, as with career salary growth. Compounds annually.'

function ChangeRow({
  change,
  onChange,
  onRemove,
}: {
  change: ContributionChange
  onChange: (change: ContributionChange) => void
  onRemove: () => void
}) {
  return (
    <div className="field-row" style={{ alignItems: 'flex-end' }}>
      <NumberField
        label="from age"
        value={change.age}
        onChange={(v) => onChange({ ...change, age: v ?? 0 })}
        min={0}
        width={90}
      />
      <NumberField
        label="new annual amount"
        value={change.annual_amount}
        onChange={(v) => onChange({ ...change, annual_amount: v ?? 0 })}
        suffix="$/yr"
        group
        min={0}
        width={150}
      />
      <NumberField
        label="extra increase"
        value={change.extra_annual_increase}
        onChange={(v) => onChange({ ...change, extra_annual_increase: v })}
        percent
        width={120}
        info={EXTRA_INCREASE_INFO}
      />
      <CheckField
        label="index to inflation"
        checked={change.index_to_inflation ?? true}
        onChange={(on) => onChange({ ...change, index_to_inflation: on })}
        info={INDEX_INFO}
      />
      <button className="subtle" style={{ marginBottom: 6 }} onClick={onRemove}>
        ✕
      </button>
    </div>
  )
}

export function ContributionsForm({ contributions, accountNames, onChange }: Props) {
  const update = (i: number, next: Contribution) =>
    onChange(contributions.map((c, j) => (j === i ? next : c)))

  // A contribution may instead carry salary + savings_rate (salary mode);
  // read them defensively so the total stays correct for either form.
  const annual = (c: Contribution) => {
    const { salary, savings_rate: rate } = c as { salary?: number; savings_rate?: number }
    return c.annual_amount ?? (salary != null && rate != null ? salary * rate : 0)
  }
  const totalAnnual = contributions.reduce((sum, c) => sum + annual(c), 0)

  return (
    <section className="card">
      <div className="section-head">
        <h3>Contributions</h3>
        <span className="section-total">
          Total <strong>{money(totalAnnual)}</strong>/yr
        </span>
      </div>
      <p className="hint">
        Annual amounts in today's dollars (multiply monthly figures by 12); they stop at
        retirement. Scheduled changes reset the amount from a future age — e.g. a CoastFI
        downshift.
      </p>
      {contributions.map((contribution, i) => (
        <div key={i} className="subcard">
          <div className="subcard-head">
            <strong>→ {contribution.account}</strong>
            <button
              className="subtle"
              onClick={() => onChange(contributions.filter((_, j) => j !== i))}
            >
              ✕ remove
            </button>
          </div>
          <div className="field-row" style={{ alignItems: 'flex-end' }}>
            <SelectField
              label="account"
              value={contribution.account}
              options={accountNames}
              onChange={(account) => update(i, { ...contribution, account })}
              width={170}
            />
            <NumberField
              label="annual amount"
              value={contribution.annual_amount}
              onChange={(v) => update(i, { ...contribution, annual_amount: v ?? 0 })}
              suffix="$/yr"
              group
              min={0}
              width={150}
            />
            <NumberField
              label="extra increase"
              value={contribution.extra_annual_increase}
              onChange={(v) => update(i, { ...contribution, extra_annual_increase: v })}
              percent
              width={120}
              info={EXTRA_INCREASE_INFO}
            />
            <CheckField
              label="index to inflation"
              checked={contribution.index_to_inflation ?? true}
              onChange={(on) => update(i, { ...contribution, index_to_inflation: on })}
              info={INDEX_INFO}
            />
          </div>
          {(contribution.changes ?? []).map((change, k) => (
            <ChangeRow
              key={k}
              change={change}
              onChange={(next) =>
                update(i, {
                  ...contribution,
                  changes: (contribution.changes ?? []).map((c, m) => (m === k ? next : c)),
                })
              }
              onRemove={() =>
                update(i, {
                  ...contribution,
                  changes: (contribution.changes ?? []).filter((_, m) => m !== k),
                })
              }
            />
          ))}
          <button
            className="add-btn"
            onClick={() => {
              const last = contribution.changes?.[contribution.changes.length - 1]
              update(i, {
                ...contribution,
                changes: [
                  ...(contribution.changes ?? []),
                  {
                    age: (last?.age ?? 45) + 5,
                    annual_amount: contribution.annual_amount,
                    index_to_inflation: contribution.index_to_inflation ?? true,
                  },
                ],
              })
            }}
          >
            + schedule a change
          </button>
        </div>
      ))}
      <button
        className="add-btn"
        disabled={accountNames.length === 0}
        onClick={() =>
          onChange([
            ...contributions,
            { account: accountNames[0], annual_amount: 10000, index_to_inflation: true },
          ])
        }
      >
        + add contribution
      </button>
    </section>
  )
}
