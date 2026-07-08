import { useState } from 'react'
import { money, percent } from '../../format'
import { SCENARIOS } from '../../palette'
import type { Basis, ResultsPayload } from '../../types'
import { FanChart } from './FanChart'
import { Histogram } from './Histogram'
import { ScenarioChart } from './ScenarioChart'

const scenarioLabel = (percentile: number) =>
  SCENARIOS.find((s) => s.percentile === percentile)?.label ?? `${percentile}th percentile market`

export function ResultsView({ results }: { results: ResultsPayload }) {
  const [basis, setBasis] = useState<Basis>('real')
  const dollars = basis === 'real' ? "today's dollars" : 'nominal dollars'
  const bands = results.bands[basis]
  const confidence = results.confidence[basis]

  return (
    <div className="results">
      <h2>Results</h2>
      <div className="headline">
        <span className={`prob ${results.score.severity}`}>
          {percent(results.success_probability)}
          <small className="prob-label">{results.score.label}</small>
        </span>
        <span className="goal-text">
          chance of success — goal: {results.goal.text}
          {results.failed_paths > 0 && results.median_depletion_age !== null && (
            <>
              {' '}
              ({results.failed_paths.toLocaleString('en-US')} of{' '}
              {results.n_sims.toLocaleString('en-US')} paths failed; median depletion age{' '}
              {Math.round(results.median_depletion_age)})
            </>
          )}
        </span>
      </div>
      <div className="result-meta">
        At {percent(results.confidence.level, 0)} confidence
        (significantly-below-average market): <strong>{money(confidence)}</strong> left at age{' '}
        {results.confidence.age}, {dollars}.
      </div>
      <div className="result-meta">
        {results.n_sims.toLocaleString('en-US')} simulations
        {results.seed !== null && <> · seed {results.seed}</>} · starting balance{' '}
        {money(results.starting_balance)} ·{' '}
        <span className="toggle">
          <button className={basis === 'real' ? 'active' : ''} onClick={() => setBasis('real')}>
            today's $
          </button>
          <button
            className={basis === 'nominal' ? 'active' : ''}
            onClick={() => setBasis('nominal')}
          >
            nominal $
          </button>
        </span>
      </div>

      <div className="chart-card">
        <h3>Portfolio balance by age</h3>
        <p className="sub">
          Median and 10–90 / 25–75 percentile bands across {results.n_sims.toLocaleString('en-US')}{' '}
          simulated paths, {dollars}
        </p>
        <FanChart ages={results.ages} bands={bands} markers={results.markers} />
      </div>

      <div className="chart-card">
        <h3>Market scenario projections</h3>
        <p className="sub">
          Total balance if markets perform at the given percentile of simulated paths, {dollars}
        </p>
        <ScenarioChart ages={results.ages} bands={bands} markers={results.markers} />
      </div>

      {results.max_withdrawal && (
        <div className="chart-card">
          <h3>Maximum sustainable withdrawal (die-with-zero)</h3>
          <p className="sub">
            Largest inflation-adjusted withdrawal that draws each scenario's retirement balance down
            to about zero over {results.max_withdrawal.n_years} years. Always in today's dollars —
            independent of the toggle above.
          </p>
          <div className="tables-row">
            {results.max_withdrawal.scenarios.map((scenario) => (
              <div key={scenario.percentile} className="chart-card">
                <h3>{scenarioLabel(scenario.percentile)}</h3>
                <p className="sub">{money(scenario.start_balance)} at retirement</p>
                <table className="mini">
                  <thead>
                    <tr>
                      <th>percentile</th>
                      <th className="num">monthly (today's $)</th>
                      <th className="num">rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scenario.rows.map((row) => (
                      <tr key={row.percentile}>
                        <td>{row.percentile}th</td>
                        <td className="num">{money(row.monthly)}</td>
                        <td className="num">{percent(row.rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="chart-card">
        <h3>
          Ending balance at {results.histogram.at} (age {results.histogram.age})
        </h3>
        <p className="sub">
          Distribution across {results.n_sims.toLocaleString('en-US')} simulated paths, {dollars}
        </p>
        <Histogram histogram={results.histogram[basis]} nSims={results.n_sims} />
      </div>

      <div className="tables-row">
        {results.tables.map((table) => (
          <div key={table.title} className="chart-card">
            <h3>{table.title}</h3>
            <table className="mini">
              <thead>
                <tr>
                  <th>percentile</th>
                  <th className="num">today's $</th>
                  <th className="num">nominal $</th>
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row) => (
                  <tr key={row.percentile}>
                    <td>{row.percentile}th</td>
                    <td className="num">{money(row.real)}</td>
                    <td className="num">{money(row.nominal)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
        <div className="chart-card">
          <h3>Market assumptions (nominal, annual)</h3>
          <table className="mini">
            <thead>
              <tr>
                <th>series</th>
                <th className="num">mean</th>
                <th className="num">vol</th>
              </tr>
            </thead>
            <tbody>
              {results.assumptions.map((a) => (
                <tr key={a.series}>
                  <td>{a.series}</td>
                  <td className="num">{percent(a.mean)}</td>
                  <td className="num">{percent(a.vol)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
