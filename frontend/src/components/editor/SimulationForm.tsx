import type { RawConfig } from '../../types'
import { CollapsibleCard } from './CollapsibleCard'
import { NumberField } from './Fields'

interface Props {
  simulation: RawConfig['simulation']
  onChange: (value: RawConfig['simulation']) => void
}

export function SimulationForm({ simulation, onChange }: Props) {
  return (
    <CollapsibleCard id="simulation" title="Simulation">
      <p className="hint">Set a seed for a reproducible draw; clear it for a fresh one each run.</p>
      <div className="field-row">
        <NumberField
          label="simulations"
          value={simulation?.n_sims}
          onChange={(v) => onChange({ ...simulation, n_sims: v })}
          placeholder="10000"
          group
          min={1}
        />
        <NumberField
          label="seed (optional)"
          value={simulation?.seed ?? undefined}
          onChange={(v) => onChange({ ...simulation, seed: v ?? null })}
          placeholder="random"
        />
      </div>
    </CollapsibleCard>
  )
}
