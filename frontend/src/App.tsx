import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from './api'
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
import { ResultsView } from './components/results/ResultsView'
import {
  downloadFile,
  loadPlans,
  loadSelected,
  localSerialize,
  newId,
  parseUpload,
  savePlans,
  templateConfig,
} from './storage'
import type { Plan, RawConfig, ResultsPayload, Schema } from './types'

export default function App() {
  const [schema, setSchema] = useState<Schema | null>(null)
  const [plans, setPlans] = useState<Plan[]>(() => loadPlans())
  const [selected, setSelected] = useState<string | null>(() => loadSelected())
  const [draft, setDraft] = useState<RawConfig | null>(null)
  // "dirty" now means edited since the last download — the plan itself is
  // always persisted to localStorage, so nothing is lost by switching plans.
  const [dirty, setDirty] = useState(false)
  const [tab, setTab] = useState<'form' | 'yaml'>('form')
  const [validationError, setValidationError] = useState<string | null>(null)
  const [banner, setBanner] = useState<{ kind: 'error' | 'ok'; text: string } | null>(null)
  const [results, setResults] = useState<ResultsPayload | null>(null)
  const [running, setRunning] = useState(false)
  const [runSims, setRunSims] = useState<number | undefined>(undefined)
  const [runSeed, setRunSeed] = useState<number | undefined>(undefined)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api
      .schema()
      .then(setSchema)
      .catch((error) => setBanner({ kind: 'error', text: `could not reach server: ${error.message}` }))
  }, [])

  // Load the initially-selected plan's config into the editable draft once.
  useEffect(() => {
    const initial = plans.find((p) => p.id === selected) ?? plans[0]
    if (initial) {
      setSelected(initial.id)
      setDraft(initial.config)
    }
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

  // Single writer for plan state: keep React state and localStorage in lockstep.
  const persist = (nextPlans: Plan[], nextSelected: string | null) => {
    setPlans(nextPlans)
    setSelected(nextSelected)
    savePlans(nextPlans, nextSelected)
  }

  const selectPlan = (id: string) => {
    if (id === selected) return
    const plan = plans.find((p) => p.id === id)
    if (!plan) return
    setSelected(id)
    savePlans(plans, id)
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
      persist(
        plans.map((p) => (p.id === selected ? { ...p, config: next } : p)),
        selected,
      )
    }
  }

  const addPlan = (name: string, config: RawConfig) => {
    const plan: Plan = { id: newId(), name, config }
    persist([...plans, plan], plan.id)
    setDraft(config)
    setDirty(true)
    setResults(null)
    setBanner(null)
  }

  const create = () => {
    const name = window.prompt('Name for the new plan (e.g. my_plan):')
    if (!name) return
    addPlan(name.replace(/\.yaml$/, ''), templateConfig())
  }

  const duplicate = () => {
    const current = plans.find((p) => p.id === selected)
    if (!current) return
    const name = window.prompt('Name for the copy:', `${current.name}_copy`)
    if (!name) return
    // Deep clone so edits to the copy don't touch the original.
    addPlan(name.replace(/\.yaml$/, ''), structuredClone(current.config))
  }

  const rename = () => {
    const current = plans.find((p) => p.id === selected)
    if (!current) return
    const name = window.prompt('New name for this plan:', current.name)
    if (!name || name === current.name) return
    persist(
      plans.map((p) => (p.id === current.id ? { ...p, name: name.replace(/\.yaml$/, '') } : p)),
      selected,
    )
  }

  const remove = () => {
    const current = plans.find((p) => p.id === selected)
    if (!current) return
    if (!window.confirm(`Remove "${current.name}" from this browser? Download it first to keep a copy.`))
      return
    const remaining = plans.filter((p) => p.id !== current.id)
    const nextSelected = remaining[0]?.id ?? null
    persist(remaining, nextSelected)
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
      const plan: Plan = { id: newId(), name, config }
      persist([...plans, plan], plan.id)
      setDraft(config)
      setDirty(false)
      setResults(null)
      setBanner({ kind: 'ok', text: `loaded ${file.name}` })
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
    setBanner(null)
    try {
      setResults(await api.simulate(draft, runSims, runSeed))
    } catch (error) {
      const message = error instanceof ApiError ? error.message : String(error)
      setBanner({ kind: 'error', text: `simulation failed — ${message}` })
    } finally {
      setRunning(false)
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
        onSelect={selectPlan}
        onCreate={create}
        onDuplicate={duplicate}
        onRename={rename}
        onDelete={remove}
        onUpload={upload}
      />
      <main>
        {!draft || !schema ? (
          <div className="empty-state">
            {schema
              ? 'Create a new plan, or upload a plan YAML file to get started.'
              : 'Connecting to server…'}
          </div>
        ) : (
          <>
            <div className="topbar">
              <h2>{currentName}</h2>
              {dirty && <span className="dirty">not downloaded</span>}
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
            </div>

            {results && <ResultsView results={results} />}
          </>
        )}
      </main>
    </>
  )
}
