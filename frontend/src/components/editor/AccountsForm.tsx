import type { Account, GlidePoint, Person, Schema } from '../../types'
import { NumberField, SelectField, TextField } from './Fields'

interface Props {
  accounts: Account[]
  person: Person
  schema: Schema
  onChange: (accounts: Account[]) => void
}

function AllocationEditor({
  allocation,
  assetClasses,
  onChange,
}: {
  allocation: Record<string, number>
  assetClasses: string[]
  onChange: (allocation: Record<string, number>) => void
}) {
  const sum = Object.values(allocation).reduce((a, b) => a + (b || 0), 0)
  const bad = Math.abs(sum - 1) > 1e-6
  return (
    <div className="field-row" style={{ alignItems: 'flex-end', marginBottom: 4 }}>
      {assetClasses.map((asset) => (
        <NumberField
          key={asset}
          label={asset}
          value={allocation[asset]}
          onChange={(v) => {
            const next = { ...allocation }
            if (v === undefined) delete next[asset]
            else next[asset] = v
            onChange(next)
          }}
          percent
          min={0}
          width={110}
        />
      ))}
      <span className={`alloc-sum${bad ? ' bad' : ''}`} style={{ paddingBottom: 8 }}>
        sum {parseFloat((sum * 100).toPrecision(6))}%{bad ? ' — must be 100%' : ''}
      </span>
    </div>
  )
}

function AccountCard({
  account,
  person,
  schema,
  onChange,
  onRemove,
}: {
  account: Account
  person: Person
  schema: Schema
  onChange: (account: Account) => void
  onRemove: () => void
}) {
  const usesGlide = account.glide_path !== undefined

  const toggleMode = (glide: boolean) => {
    if (glide === usesGlide) return
    if (glide) {
      const allocation = account.allocation ?? { [schema.asset_classes[0]]: 1 }
      const points: GlidePoint[] = [
        { age: person.current_age, allocation: { ...allocation } },
        { age: person.retirement_age, allocation: { ...allocation } },
      ]
      const { allocation: _dropped, ...rest } = account
      onChange({ ...rest, glide_path: points })
    } else {
      const allocation = account.glide_path?.[0]?.allocation ?? { [schema.asset_classes[0]]: 1 }
      const { glide_path: _dropped, ...rest } = account
      onChange({ ...rest, allocation: { ...allocation } })
    }
  }

  const setPoint = (index: number, point: GlidePoint) => {
    const points = [...(account.glide_path ?? [])]
    points[index] = point
    onChange({ ...account, glide_path: points })
  }

  return (
    <div className="subcard">
      <div className="subcard-head">
        <strong>{account.name || 'unnamed account'}</strong>
        <button className="subtle" onClick={onRemove} title="remove account">
          ✕ remove
        </button>
      </div>
      <div className="field-row">
        <TextField
          label="name"
          value={account.name}
          onChange={(name) => onChange({ ...account, name })}
          width={170}
        />
        <SelectField
          label="type"
          value={account.type}
          options={schema.account_types}
          onChange={(type) => onChange({ ...account, type })}
          width={140}
        />
        <NumberField
          label="starting balance"
          value={account.balance}
          onChange={(v) => onChange({ ...account, balance: v ?? 0 })}
          suffix="$"
          min={0}
          width={150}
        />
        <SelectField
          label="allocation mode"
          value={usesGlide ? 'glide path' : 'fixed'}
          options={['fixed', 'glide path']}
          onChange={(mode) => toggleMode(mode === 'glide path')}
          width={130}
        />
      </div>

      {!usesGlide && account.allocation && (
        <AllocationEditor
          allocation={account.allocation}
          assetClasses={schema.asset_classes}
          onChange={(allocation) => onChange({ ...account, allocation })}
        />
      )}

      {usesGlide &&
        (account.glide_path ?? []).map((point, i) => (
          <div key={i} className="field-row" style={{ alignItems: 'flex-end' }}>
            <NumberField
              label="at age"
              value={point.age}
              onChange={(v) => setPoint(i, { ...point, age: v ?? 0 })}
              min={0}
              width={90}
            />
            <div style={{ flex: 1 }}>
              <AllocationEditor
                allocation={point.allocation}
                assetClasses={schema.asset_classes}
                onChange={(allocation) => setPoint(i, { ...point, allocation })}
              />
            </div>
            <button
              className="subtle"
              style={{ marginBottom: 8 }}
              disabled={(account.glide_path ?? []).length <= 1}
              onClick={() =>
                onChange({
                  ...account,
                  glide_path: (account.glide_path ?? []).filter((_, j) => j !== i),
                })
              }
            >
              ✕
            </button>
          </div>
        ))}
      {usesGlide && (
        <button
          className="add-btn"
          onClick={() => {
            const points = account.glide_path ?? []
            const last = points[points.length - 1]
            onChange({
              ...account,
              glide_path: [
                ...points,
                { age: (last?.age ?? person.current_age) + 10, allocation: { ...last?.allocation } },
              ],
            })
          }}
        >
          + add glide point
        </button>
      )}
    </div>
  )
}

export function AccountsForm({ accounts, person, schema, onChange }: Props) {
  return (
    <section className="card">
      <h3>Accounts</h3>
      <p className="hint">
        Account types are labels only — taxes are not modeled. Each account has either a fixed
        allocation or a glide path interpolated between age points.
      </p>
      {accounts.map((account, i) => (
        <AccountCard
          key={i}
          account={account}
          person={person}
          schema={schema}
          onChange={(next) => onChange(accounts.map((a, j) => (j === i ? next : a)))}
          onRemove={() => onChange(accounts.filter((_, j) => j !== i))}
        />
      ))}
      <button
        className="add-btn"
        onClick={() =>
          onChange([
            ...accounts,
            {
              name: `account_${accounts.length + 1}`,
              type: 'brokerage',
              balance: 0,
              allocation: { [schema.asset_classes[0]]: 1 },
            },
          ])
        }
      >
        + add account
      </button>
    </section>
  )
}
