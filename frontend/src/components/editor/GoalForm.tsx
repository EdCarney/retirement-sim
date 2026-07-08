import type { Goal, Person, Schema } from '../../types'
import { CollapsibleCard } from './CollapsibleCard'
import { NumberField, SelectField } from './Fields'

interface Props {
  goal: Goal
  person: Person
  schema: Schema
  onChange: (goal: Goal) => void
  onPersonChange: (person: Person) => void
}

export function GoalForm({ goal, person, schema, onChange, onPersonChange }: Props) {
  const setType = (type: string) => {
    if (type === goal.type) return
    onChange(
      type === 'retirement_income'
        ? { type, monthly_income_today: goal.monthly_income_today ?? 5000 }
        : { type, amount: goal.amount ?? 1_000_000, basis: goal.basis ?? 'real' },
    )
  }
  const setAge = (field: 'retirement_age' | 'death_age') => (value: number | undefined) =>
    onPersonChange({ ...person, [field]: value ?? 0 })
  return (
    <CollapsibleCard id="goal" title="Goal">
      <p className="hint">
        Either sustain a monthly income (today's dollars) from retirement to death, or reach a
        total amount by retirement.
      </p>
      <div className="field-row">
        <NumberField
          label="retirement age"
          value={person.retirement_age}
          onChange={setAge('retirement_age')}
          min={0}
        />
        <NumberField label="death age" value={person.death_age} onChange={setAge('death_age')} min={0} />
      </div>
      <div className="field-row">
        <SelectField label="type" value={goal.type} options={schema.goal_types} onChange={setType} width={190} />
        {goal.type === 'retirement_income' ? (
          <NumberField
            label="monthly income (today's $)"
            value={goal.monthly_income_today}
            onChange={(v) => onChange({ ...goal, monthly_income_today: v })}
            suffix="$/mo"
            group
            min={0}
          />
        ) : (
          <>
            <NumberField
              label="target amount"
              value={goal.amount}
              onChange={(v) => onChange({ ...goal, amount: v })}
              suffix="$"
              group
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
    </CollapsibleCard>
  )
}
