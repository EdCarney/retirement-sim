import { useCallback, useEffect, useRef, useState } from 'react'
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
import type { ConfigListEntry, RawConfig, ResultsPayload, Schema } from './types'

export default function App() {
  const [schema, setSchema] = useState<Schema | null>(null)
  const [configs, setConfigs] = useState<ConfigListEntry[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [draft, setDraft] = useState<RawConfig | null>(null)
  const [dirty, setDirty] = useState(false)
  const [tab, setTab] = useState<'form' | 'yaml'>('form')
  const [validationError, setValidationError] = useState<string | null>(null)
  const [banner, setBanner] = useState<{ kind: 'error' | 'ok'; text: string } | null>(null)
  const [results, setResults] = useState<ResultsPayload | null>(null)
  const [running, setRunning] = useState(false)
  const [runSims, setRunSims] = useState<number | undefined>(undefined)
  const [runSeed, setRunSeed] = useState<number | undefined>(undefined)

  const refreshList = useCallback(async () => {
    setConfigs(await api.listConfigs())
  }, [])

  useEffect(() => {
    Promise.all([api.schema(), api.listConfigs()])
      .then(([loadedSchema, list]) => {
        setSchema(loadedSchema)
        setConfigs(list)
      })
      .catch((error) => setBanner({ kind: 'error', text: `could not reach server: ${error.message}` }))
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

  const confirmDiscard = () =>
    !dirty || window.confirm('Discard unsaved changes to the current config?')

  const selectConfig = async (name: string) => {
    if (name === selected || !confirmDiscard()) return
    try {
      const file = await api.getConfig(name)
      setSelected(name)
      setDraft(file.config)
      setDirty(false)
      setResults(null)
      setBanner(null)
      setValidationError(file.error)
    } catch (error) {
      setBanner({ kind: 'error', text: (error as Error).message })
    }
  }

  const updateDraft = (next: RawConfig) => {
    setDraft(next)
    setDirty(true)
    setBanner(null)
  }

  const save = async () => {
    if (!selected || !draft) return
    try {
      await api.saveConfig(selected, draft)
      setDirty(false)
      setBanner({ kind: 'ok', text: `saved ${selected}` })
      refreshList()
    } catch (error) {
      const message = error instanceof ApiError ? error.message : String(error)
      setBanner({ kind: 'error', text: `not saved — ${message}` })
    }
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

  const create = async () => {
    const name = window.prompt('Name for the new config (e.g. my_plan):')
    if (!name) return
    const file = name.endsWith('.yaml') ? name : `${name}.yaml`
    try {
      await api.createConfig(file)
      await refreshList()
      await selectConfig(file)
    } catch (error) {
      setBanner({ kind: 'error', text: (error as Error).message })
    }
  }

  const duplicate = async () => {
    if (!selected) return
    const suggestion = selected.replace(/\.yaml$/, '_copy')
    const name = window.prompt('Name for the copy:', suggestion)
    if (!name) return
    const file = name.endsWith('.yaml') ? name : `${name}.yaml`
    try {
      await api.createConfig(file, selected)
      await refreshList()
      await selectConfig(file)
    } catch (error) {
      setBanner({ kind: 'error', text: (error as Error).message })
    }
  }

  const rename = async () => {
    if (!selected) return
    if (!confirmDiscard()) return
    const current = selected.replace(/\.yaml$/, '')
    const name = window.prompt('New name for this config:', current)
    if (!name || name === current) return
    const file = name.endsWith('.yaml') ? name : `${name}.yaml`
    try {
      await api.renameConfig(selected, file)
      setSelected(null)
      setDirty(false)
      await refreshList()
      await selectConfig(file)
    } catch (error) {
      setBanner({ kind: 'error', text: (error as Error).message })
    }
  }

  const remove = async () => {
    if (!selected) return
    if (!window.confirm(`Delete ${selected}? The file is removed from disk.`)) return
    try {
      await api.deleteConfig(selected)
      setSelected(null)
      setDraft(null)
      setResults(null)
      setDirty(false)
      refreshList()
    } catch (error) {
      setBanner({ kind: 'error', text: (error as Error).message })
    }
  }

  const accountNames = draft?.accounts.map((a) => a.name) ?? []

  return (
    <>
      <ConfigList
        configs={configs}
        selected={selected}
        onSelect={selectConfig}
        onCreate={create}
        onDuplicate={duplicate}
        onRename={rename}
        onDelete={remove}
      />
      <main>
        {!draft || !schema ? (
          <div className="empty-state">
            {schema ? 'Select a config on the left, or create a new one.' : 'Connecting to server…'}
          </div>
        ) : (
          <>
            <div className="topbar">
              <h2>{selected?.replace(/\.yaml$/, '')}</h2>
              {dirty && <span className="dirty">unsaved changes</span>}
              <span className="spacer" />
              <button className="primary" onClick={save} disabled={!dirty || validationError !== null}>
                Save
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
              {dirty && (
                <span className="dirty" style={{ paddingBottom: 8 }}>
                  runs the edited (unsaved) config
                </span>
              )}
            </div>

            {results && <ResultsView results={results} />}
          </>
        )}
      </main>
    </>
  )
}
