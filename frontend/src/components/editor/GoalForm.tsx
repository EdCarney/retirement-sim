import type { Goal, Schema } from '../../types'
import { NumberField, SelectField } from './Fields'

interface Props {
  goal: Goal
  schema: Schema
  onChange: (goal: Goal) => void
}

export function GoalForm({ goal, schema, onChange }: Props) {
  const setType = (type: string) => {
    if (type === goal.type) return
    onChange(
      type === 'retirement_income'
        ? { type, monthly_income_today: goal.monthly_income_today ?? 5000 }
        : { type, amount: goal.amount ?? 1_000_000, basis: goal.basis ?? 'real' },
    )
  }
  return (
    <section className="card">
      <h3>Goal</h3>
      <p className="hint">
        Either sustain a monthly income (today's dollars) from retirement to death, or reach a
        total amount by retirement.
      </p>
      <div className="field-row">
        <SelectField label="type" value={goal.type} options={schema.goal_types} onChange={setType} width={190} />
        {goal.type === 'retirement_income' ? (
          <NumberField
            label="monthly income (today's $)"
            value={goal.monthly_income_today}
            onChange={(v) => onChange({ ...goal, monthly_income_today: v })}
            suffix="$/mo"
            min={0}
          />
        ) : (
          <>
            <NumberField
              label="target amount"
              value={goal.amount}
              onChange={(v) => onChange({ ...goal, amount: v })}
              suffix="$"
              min={0}
            />
            <SelectField
              label="basis"
              value={goal.basis ?? 'real'}
              options={schema.goal_bases}
              onChange={(basis) => onChange({ ...goal, basis })}
              width={120}
            />
          </>
        )}
      </div>
    </section>
  )
}
