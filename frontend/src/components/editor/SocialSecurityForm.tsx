import type { SocialSecurity } from '../../types'
import { CheckField, NumberField } from './Fields'

interface Props {
  socialSecurity: SocialSecurity | undefined
  onChange: (value: SocialSecurity | undefined) => void
}

export function SocialSecurityForm({ socialSecurity, onChange }: Props) {
  const enabled = socialSecurity !== undefined
  return (
    <section className="card">
      <h3>Social Security</h3>
      <p className="hint">
        Optional. The benefit is COLA'd along each path's simulated inflation and offsets
        withdrawals.
      </p>
      <div className="field-row">
        <CheckField
          label="model Social Security"
          checked={enabled}
          onChange={(on) =>
            onChange(on ? { monthly_benefit_today: 2000, claiming_age: 67 } : undefined)
          }
        />
        {enabled && (
          <>
            <NumberField
              label="monthly benefit (today's $)"
              value={socialSecurity.monthly_benefit_today}
              onChange={(v) => onChange({ ...socialSecurity, monthly_benefit_today: v ?? 0 })}
              suffix="$/mo"
              min={0}
            />
            <NumberField
              label="claiming age"
              value={socialSecurity.claiming_age}
              onChange={(v) => onChange({ ...socialSecurity, claiming_age: v ?? 0 })}
              min={0}
            />
          </>
        )}
      </div>
    </section>
  )
}
