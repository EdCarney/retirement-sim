import type { Person } from '../../types'
import { NumberField } from './Fields'

interface Props {
  person: Person
  onChange: (person: Person) => void
}

export function PersonForm({ person, onChange }: Props) {
  const set = (field: keyof Person) => (value: number | undefined) =>
    onChange({ ...person, [field]: value ?? 0 })
  return (
    <section className="card">
      <h3>Person</h3>
      <p className="hint">Ages defining the planning horizon.</p>
      <div className="field-row">
        <NumberField label="current age" value={person.current_age} onChange={set('current_age')} min={0} />
        <NumberField
          label="retirement age"
          value={person.retirement_age}
          onChange={set('retirement_age')}
          min={0}
        />
        <NumberField label="death age" value={person.death_age} onChange={set('death_age')} min={0} />
      </div>
    </section>
  )
}
