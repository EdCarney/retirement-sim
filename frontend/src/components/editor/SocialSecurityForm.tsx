import type { SocialSecurity } from '../../types'
import { CollapsibleCard } from './CollapsibleCard'
import { CheckField, InfoTip, NumberField, SelectField } from './Fields'

interface Props {
  socialSecurity: SocialSecurity | undefined
  onChange: (value: SocialSecurity | undefined) => void
}

const DIRECT = 'direct benefit'
const PIA = 'estimate from PIA'
const MODES = [DIRECT, PIA]

// Mirror of retirement_sim.config._ss_benefit_factor: the fraction of the PIA
// received when claiming at `claimingAge`, given a full-retirement age (FRA).
// Early claiming is reduced 5/9%/mo for the first 36 months and 5/12%/mo
// beyond; claiming after FRA earns 2/3%/mo delayed credits, capped at age 70.
function benefitFactor(claimingAge: number, fra: number): number {
  const months = Math.round((claimingAge - fra) * 12)
  if (months < 0) {
    const early = -months
    const first = Math.min(early, 36)
    const beyond = early - first
    return 1 - (first * (5 / 900) + beyond * (5 / 1200))
  }
  const delayed = Math.min(months, Math.round((70 - fra) * 12))
  return 1 + Math.max(delayed, 0) * (2 / 300)
}

export function SocialSecurityForm({ socialSecurity, onChange }: Props) {
  // `present` means the config carries benefit values at all; `active` means
  // they should affect the plan. Toggling off keeps the values (greyed) so the
  // benefit can be switched back on without re-entering them.
  const present = socialSecurity !== undefined
  const active = present && socialSecurity.enabled !== false
  const isPia = present && socialSecurity.pia_monthly !== undefined

  const toggle = (on: boolean) => {
    if (on) {
      if (socialSecurity) {
        // Re-enable in place. Omit `enabled` (defaults true) to keep YAML clean.
        const next = { ...socialSecurity }
        delete next.enabled
        onChange(next)
      } else {
        onChange({ monthly_benefit_today: 2000, claiming_age: 67 })
      }
    } else if (socialSecurity) {
      onChange({ ...socialSecurity, enabled: false })
    }
  }

  const setMode = (mode: string) => {
    if (!socialSecurity) return
    if (mode === PIA) {
      if (socialSecurity.pia_monthly !== undefined) return
      onChange({
        pia_monthly: socialSecurity.monthly_benefit_today ?? 2000,
        claiming_age: socialSecurity.claiming_age,
        full_retirement_age: 67,
      })
    } else {
      if (socialSecurity.pia_monthly === undefined) return
      onChange({
        monthly_benefit_today: socialSecurity.pia_monthly,
        claiming_age: socialSecurity.claiming_age,
      })
    }
  }

  const fra = socialSecurity?.full_retirement_age ?? 67
  const derived =
    isPia && socialSecurity.pia_monthly !== undefined
      ? socialSecurity.pia_monthly * benefitFactor(socialSecurity.claiming_age, fra)
      : undefined

  return (
    <CollapsibleCard id="social-security" title="Social Security">
      <p className="hint">
        Optional. The benefit is COLA'd
        <InfoTip text="COLA — Cost-of-Living Adjustment: the annual inflation raise Social Security applies to benefits. Here each simulated path grows the benefit by its own simulated inflation." />{' '}
        along each path's simulated inflation and offsets withdrawals.
      </p>
      <div className="field-row">
        <CheckField label="model Social Security" checked={active} onChange={toggle} />
        {present && (
          <>
            <SelectField
              label="benefit source"
              value={isPia ? PIA : DIRECT}
              options={MODES}
              onChange={setMode}
              width={180}
              disabled={!active}
            />
            {isPia ? (
              <>
                <NumberField
                  label="PIA (benefit at FRA, today's $)"
                  value={socialSecurity.pia_monthly}
                  onChange={(v) => onChange({ ...socialSecurity, pia_monthly: v ?? 0 })}
                  suffix="$/mo"
                  group
                  min={0}
                  disabled={!active}
                  info="PIA — Primary Insurance Amount: the monthly benefit you'd get if you claim exactly at your full retirement age. The SSA computes it from your 35 highest-earning years."
                />
                <NumberField
                  label="claiming age"
                  value={socialSecurity.claiming_age}
                  onChange={(v) => onChange({ ...socialSecurity, claiming_age: v ?? 0 })}
                  min={62}
                  step={1}
                  disabled={!active}
                  info="The age you start taking Social Security (62–70). Claiming before your full retirement age permanently reduces the benefit; delaying past it earns credits up to age 70."
                />
                <NumberField
                  label="full retirement age"
                  value={socialSecurity.full_retirement_age ?? 67}
                  onChange={(v) => onChange({ ...socialSecurity, full_retirement_age: v ?? 67 })}
                  min={62}
                  step={1}
                  disabled={!active}
                  info="FRA — Full Retirement Age: the age at which you receive 100% of your PIA. It's 67 for anyone born in 1960 or later."
                />
              </>
            ) : (
              <>
                <NumberField
                  label="monthly benefit (today's $)"
                  value={socialSecurity.monthly_benefit_today}
                  onChange={(v) => onChange({ ...socialSecurity, monthly_benefit_today: v ?? 0 })}
                  suffix="$/mo"
                  group
                  min={0}
                  disabled={!active}
                />
                <NumberField
                  label="claiming age"
                  value={socialSecurity.claiming_age}
                  onChange={(v) => onChange({ ...socialSecurity, claiming_age: v ?? 0 })}
                  min={0}
                  disabled={!active}
                  info="The age you start taking Social Security. The benefit above is treated as the amount received at this age."
                />
              </>
            )}
          </>
        )}
      </div>
      {active && isPia && (
        <p className="hint">
          {derived !== undefined && (socialSecurity.claiming_age < 62 || socialSecurity.claiming_age > 70)
            ? 'Claiming age must be 62–70 when estimating from PIA.'
            : `Estimated benefit at claiming age ${socialSecurity.claiming_age}: ` +
              `$${Math.round(derived ?? 0).toLocaleString()}/mo ` +
              `(${Math.round(benefitFactor(socialSecurity.claiming_age, fra) * 100)}% of PIA).`}
        </p>
      )}
    </CollapsibleCard>
  )
}
