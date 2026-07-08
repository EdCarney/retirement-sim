import { useEffect, useRef, useState } from 'react'
import { api, ApiError, setUnauthorizedHandler } from './api'
import { ConfigList } from './components/ConfigList'
import { AccountsForm } from './components/editor/AccountsForm'
import { ContributionsForm } from './components/editor/ContributionsForm'
import { NumberField } from './components/editor/Fields'
import { GoalForm } from './components/editor/GoalForm'
import { MarketForm } from './components/editor/MarketForm'
import { PersonForm } from './components/editor/PersonForm'
import { SimulationForm } from './components/editor/SimulationForm'
import { SocialSecurityForm } from './components/editor/SocialSecurityForm'
import { YamlPreview } from './components/editor/YamlPreview'
import { LoginScreen } from './components/LoginScreen'
import { ResultsView } from './components/results/ResultsView'
import {
  downloadFile,
  loadSelectedId,
  localSerialize,
  newId,
  parseUpload,
  saveSelectedId,
  templateConfig,
} from './storage'
import type { Plan, RawConfig, ResultsPayload, Schema, User } from './types'

// Top-level auth gate. The planner only mounts for a logged-in user, so its
// hooks (schema fetch, plan load) never run for an anonymous visitor.
export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined)

  useEffect(() => {
    // A 401 from any protected call (e.g. an expired session mid-use) drops us
    // back to the login screen.
    setUnauthorizedHandler(() => setUser(null))
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
    return () => setUnauthorizedHandler(null)
  }, [])

  if (user === undefined) {
    return (
      <div className="auth-screen">
        <p className="empty-state">Connecting…</p>
      </div>
    )
  }
  if (user === null) return <LoginScreen onAuthed={setUser} />
  return <Planner user={user} onLoggedOut={() => setUser(null)} />
}

function Planner({ user, onLoggedOut }: { user: User; onLoggedOut: () => void }) {
  const [schema, setSchema] = useState<Schema | null>(null)
  const [plans, setPlans] = useState<Plan[]>([])
  const [plansLoaded, setPlansLoaded] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [draft, setDraft] = useState<RawConfig | null>(null)
  // "dirty" means edited since the last *download* — plan edits are always
  // persisted to the server, so nothing is lost by switching plans.
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [tab, setTab] = useState<'form' | 'yaml'>('form')
  const [validationError, setValidationError] = useState<string | null>(null)
  const [banner, setBanner] = useState<{ kind: 'error' | 'ok'; text: string } | null>(null)
  const [results, setResults] = useState<ResultsPayload | null>(null)
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState(0)
  const [runSims, setRunSims] = useState<number | undefined>(undefined)
  const [runSeed, setRunSeed] = useState<number | undefined>(undefined)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api
      .schema()
      .then(setSchema)
      .catch((error) => setBanner({ kind: 'error', text: `could not reach server: ${error.message}` }))
  }, [])

  // Load this user's plans from the server once, and open the last-selected one.
  useEffect(() => {
    api
      .listPlans()
      .then((loaded) => {
        setPlans(loaded)
        const remembered = loadSelectedId()
        const initial = loaded.find((p) => p.id === remembered) ?? loaded[0]
        if (initial) {
          setSelected(initial.id)
          setDraft(initial.config)
        }
        setPlansLoaded(true)
      })
      .catch((error) => {
        if (!(error instanceof ApiError && error.status === 401)) {
          setBanner({ kind: 'error', text: `could not load your plans: ${error.message}` })
        }
        setPlansLoaded(true)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Debounced server-side validation of the draft.
  const validateTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => {
    if (!draft) return
    clearTimeout(validateTimer.current)
    validateTimer.current = setTimeout(() => {
      api
        .validate(draft)
        .then((verdict) => setValidationError(verdict.error))
        .catch(() => setValidationError(null))
    }, 400)
    return () => clearTimeout(validateTimer.current)
  }, [draft])

  // --- Debounced autosave to the server -------------------------------------
  // Edits update React state immediately and schedule a PUT ~800ms later, so a
  // burst of keystrokes is one request. The pending payload captures the plan
  // id at schedule time, and is flushed on plan switch / unload so a fast
  // switch never drops or misroutes the last edit.
  const saveTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const pendingSave = useRef<{ id: string; name: string; config: RawConfig } | null>(null)

  const doSave = async (payload: { id: string; name: string; config: RawConfig }) => {
    setSaving(true)
    try {
      await api.updatePlan(payload.id, { name: payload.name, config: payload.config })
    } catch (error) {
      // A 401 already bounced us to login via the global handler; only surface
      // genuine save failures.
      if (!(error instanceof ApiError && error.status === 401)) {
        setBanner({ kind: 'error', text: `could not save — ${(error as Error).message}` })
      }
    } finally {
      setSaving(false)
    }
  }

  const flushSave = () => {
    clearTimeout(saveTimer.current)
    const payload = pendingSave.current
    pendingSave.current = null
    if (payload) void doSave(payload)
  }

  const cancelPendingSave = () => {
    clearTimeout(saveTimer.current)
    pendingSave.current = null
  }

  const scheduleSave = (id: string, name: string, config: RawConfig) => {
    pendingSave.current = { id, name, config }
    clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(flushSave, 800)
  }

  // Best-effort flush if the tab is closed with edits still pending.
  useEffect(() => {
    const onUnload = () => flushSave()
    window.addEventListener('beforeunload', onUnload)
    return () => {
      window.removeEventListener('beforeunload', onUnload)
      flushSave()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const selectPlan = (id: string) => {
    if (id === selected) return
    const plan = plans.find((p) => p.id === id)
    if (!plan) return
    flushSave() // persist any pending edits to the plan we're leaving
    setSelected(id)
    saveSelectedId(id)
    setDraft(plan.config)
    setDirty(false)
    setResults(null)
    setBanner(null)
  }

  const updateDraft = (next: RawConfig) => {
    setDraft(next)
    setDirty(true)
    setBanner(null)
    if (selected) {
      const name = plans.find((p) => p.id === selected)?.name ?? selected
      setPlans(plans.map((p) => (p.id === selected ? { ...p, config: next } : p)))
      scheduleSave(selected, name, next)
    }
  }

  // Create a plan on the server, then open it. Shared by new / duplicate / upload.
  const addPlan = async (name: string, config: RawConfig, opts?: { dirty?: boolean }) => {
    flushSave() // don't lose pending edits on the plan we're leaving
    try {
      const created = await api.createPlan({ id: newId(), name, config })
      setPlans((prev) => [...prev, created])
      setSelected(created.id)
      saveSelectedId(created.id)
      setDraft(created.config)
      setDirty(opts?.dirty ?? true)
      setResults(null)
      return created
    } catch (error) {
      setBanner({ kind: 'error', text: `could not create plan — ${(error as Error).message}` })
      return null
    }
  }

  const create = () => {
    const name = window.prompt('Name for the new plan (e.g. my_plan):')
    if (!name) return
    void addPlan(name.replace(/\.yaml$/, ''), templateConfig())
  }

  const duplicate = () => {
    const current = plans.find((p) => p.id === selected)
    if (!current) return
    const name = window.prompt('Name for the copy:', `${current.name}_copy`)
    if (!name) return
    // Deep clone so edits to the copy don't touch the original.
    void addPlan(name.replace(/\.yaml$/, ''), structuredClone(current.config))
  }

  const rename = async () => {
    const current = plans.find((p) => p.id === selected)
    if (!current) return
    const name = window.prompt('New name for this plan:', current.name)
    if (!name || name === current.name) return
    const cleaned = name.replace(/\.yaml$/, '')
    // This write carries the full plan, so drop any queued config save to avoid
    // a stale-name write landing after it.
    cancelPendingSave()
    try {
      const updated = await api.updatePlan(current.id, { name: cleaned, config: current.config })
      setPlans(plans.map((p) => (p.id === current.id ? updated : p)))
    } catch (error) {
      setBanner({ kind: 'error', text: `could not rename — ${(error as Error).message}` })
    }
  }

  const remove = async () => {
    const current = plans.find((p) => p.id === selected)
    if (!current) return
    if (!window.confirm(`Delete "${current.name}"? This removes it from your account.`)) return
    cancelPendingSave()
    try {
      await api.deletePlan(current.id)
    } catch (error) {
      setBanner({ kind: 'error', text: `could not delete — ${(error as Error).message}` })
      return
    }
    const remaining = plans.filter((p) => p.id !== current.id)
    const nextSelected = remaining[0]?.id ?? null
    setPlans(remaining)
    setSelected(nextSelected)
    saveSelectedId(nextSelected)
    setDraft(remaining.find((p) => p.id === nextSelected)?.config ?? null)
    setDirty(false)
    setResults(null)
    setBanner(null)
  }

  const upload = () => fileInput.current?.click()

  const onFileChosen = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = '' // allow re-uploading the same filename later
    if (!file) return
    try {
      const config = await parseUpload(file)
      const name = file.name.replace(/\.ya?ml$/i, '')
      // Uploaded plans start "clean": they already exist on the user's disk.
      const created = await addPlan(name, config, { dirty: false })
      if (created) setBanner({ kind: 'ok', text: `loaded ${file.name}` })
    } catch (error) {
      setBanner({ kind: 'error', text: `could not load file — ${(error as Error).message}` })
    }
  }

  const download = async () => {
    const current = plans.find((p) => p.id === selected)
    if (!current || !draft) return
    let text: string
    try {
      text = await api.serialize(draft)
    } catch {
      text = localSerialize(draft) // offline fallback
    }
    downloadFile(`${current.name}.yaml`, text)
    setDirty(false)
    setBanner({ kind: 'ok', text: `downloaded ${current.name}.yaml` })
  }

  const run = async () => {
    if (!draft) return
    setRunning(true)
    setProgress(0)
    setBanner(null)
    try {
      setResults(await api.simulate(draft, runSims, runSeed, setProgress))
    } catch (error) {
      const message = error instanceof ApiError ? error.message : String(error)
      setBanner({ kind: 'error', text: `simulation failed — ${message}` })
    } finally {
      setRunning(false)
    }
  }

  const logout = async () => {
    flushSave()
    try {
      await api.logout()
    } finally {
      onLoggedOut()
    }
  }

  const currentName = plans.find((p) => p.id === selected)?.name ?? ''
  const accountNames = draft?.accounts.map((a) => a.name) ?? []

  return (
    <>
      <input
        ref={fileInput}
        type="file"
        accept=".yaml,.yml"
        style={{ display: 'none' }}
        onChange={onFileChosen}
      />
      <ConfigList
        plans={plans}
        selected={selected}
        username={user.username}
        onSelect={selectPlan}
        onCreate={create}
        onDuplicate={duplicate}
        onRename={rename}
        onDelete={remove}
        onUpload={upload}
        onLogout={logout}
      />
      <main>
        {!draft || !schema ? (
          <div className="empty-state">
            {schema && plansLoaded
              ? 'Create a new plan, or upload a plan YAML file to get started.'
              : 'Connecting to server…'}
          </div>
        ) : (
          <>
            <div className="topbar">
              <h2>{currentName}</h2>
              {saving ? (
                <span className="dirty">saving…</span>
              ) : (
                dirty && <span className="dirty">not downloaded</span>
              )}
              <span className="spacer" />
              <button className="primary" onClick={download} disabled={validationError !== null}>
                Download
              </button>
            </div>

            {banner && <div className={`banner ${banner.kind}`}>{banner.text}</div>}
            {validationError && <div className="banner error">config invalid: {validationError}</div>}

            <div className="tabs">
              <button className={tab === 'form' ? 'active' : ''} onClick={() => setTab('form')}>
                Form
              </button>
              <button className={tab === 'yaml' ? 'active' : ''} onClick={() => setTab('yaml')}>
                YAML
              </button>
            </div>

            {tab === 'yaml' ? (
              <YamlPreview config={draft} />
            ) : (
              <>
                <PersonForm person={draft.person} onChange={(person) => updateDraft({ ...draft, person })} />
                <AccountsForm
                  accounts={draft.accounts}
                  person={draft.person}
                  schema={schema}
                  onChange={(accounts) => updateDraft({ ...draft, accounts })}
                />
                <ContributionsForm
                  contributions={draft.contributions ?? []}
                  accountNames={accountNames}
                  onChange={(contributions) => updateDraft({ ...draft, contributions })}
                />
                <GoalForm
                  goal={draft.goal}
                  person={draft.person}
                  schema={schema}
                  onChange={(goal) => updateDraft({ ...draft, goal })}
                  onPersonChange={(person) => updateDraft({ ...draft, person })}
                />
                <SocialSecurityForm
                  socialSecurity={draft.social_security}
                  onChange={(social_security) => {
                    const next = { ...draft }
                    if (social_security === undefined) delete next.social_security
                    else next.social_security = social_security
                    updateDraft(next)
                  }}
                />
                <MarketForm
                  market={draft.market}
                  schema={schema}
                  onChange={(market) => {
                    const next = { ...draft }
                    if (market === undefined) delete next.market
                    else next.market = market
                    updateDraft(next)
                  }}
                  feeDragBps={draft.fees?.drag_bps}
                  onFeeChange={(bps) => {
                    const next = { ...draft }
                    if (!bps) delete next.fees
                    else next.fees = { drag_bps: bps }
                    updateDraft(next)
                  }}
                />
                <SimulationForm
                  simulation={draft.simulation}
                  onChange={(simulation) => updateDraft({ ...draft, simulation })}
                />
              </>
            )}

            <div className="run-bar">
              <button className="primary" onClick={run} disabled={running || validationError !== null}>
                {running ? 'Running…' : 'Run simulation'}
              </button>
              <NumberField label="sims override" value={runSims} onChange={setRunSims} placeholder="config" min={1} />
              <NumberField label="seed override" value={runSeed} onChange={setRunSeed} placeholder="config" />
              {running && (
                <div
                  className="run-progress"
                  role="progressbar"
                  aria-valuenow={Math.round(progress * 100)}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <div className="run-progress-fill" style={{ width: `${Math.round(progress * 100)}%` }} />
                  <span className="run-progress-label">{Math.round(progress * 100)}%</span>
                </div>
              )}
            </div>

            {results && <ResultsView results={results} />}
          </>
        )}
      </main>
    </>
  )
}
