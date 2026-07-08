import type { Person } from '../../types'
import { CollapsibleCard } from './CollapsibleCard'
import { NumberField } from './Fields'

interface Props {
  person: Person
  onChange: (person: Person) => void
}

export function PersonForm({ person, onChange }: Props) {
  const set = (field: keyof Person) => (value: number | undefined) =>
    onChange({ ...person, [field]: value ?? 0 })
  return (
    <CollapsibleCard id="person" title="Person">
      <p className="hint">Your age today — the start of the planning horizon.</p>
      <div className="field-row">
        <NumberField label="current age" value={person.current_age} onChange={set('current_age')} min={0} />
      </div>
    </CollapsibleCard>
  )
}
