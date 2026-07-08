# Retirement Monte Carlo Simulator

A locally-runnable Monte Carlo simulator for evaluating retirement account goals.
You describe your accounts, contributions, and goal in a YAML config; the simulator
runs thousands of randomized market paths and reports the probability your plan
succeeds, with percentile tables and charts.

## Quick start

```bash
uv sync
uv run retirement-sim configs/example_income_goal.yaml
uv run retirement-sim configs/example_target_amount.yaml
```

Output: a terminal summary (success probability, percentile balances at retirement
and death, assumptions echo) plus three PNGs in the output directory — a fan chart
of portfolio balance percentiles by age, a Fidelity-style market-scenario chart
(average / below average / significantly below average = 50th / 25th / 10th
percentile paths), and an ending-balance histogram.

CLI overrides:

```bash
uv run retirement-sim <config.yaml> [--sims N] [--seed N] [--output-dir DIR] [--no-charts] [--show]
```

`--show` opens the charts in interactive windows (zoom/pan, blocks until closed)
in addition to saving the PNGs; `show: true` under `output:` does the same.

Note the hyphen: the command is `retirement-sim` (the package directory is
`retirement_sim` with an underscore). `uv run python -m retirement_sim <config.yaml>`
works too.

## Web UI

A local React frontend for managing configs and running simulations in the
browser, with interactive charts. Requires Node.js. Build it once:

```bash
cd frontend && npm install && npm run build && cd ..
```

Then start the server (it opens a browser tab automatically):

```bash
uv run retirement-sim-web
```

Options: `--port N` (default 8000), `--no-browser`. The server binds to
127.0.0.1 only.

Plans live **in your browser**, not on the server: the sidebar's plan list is
persisted to `localStorage`, so your work survives a reload while the backend
stays stateless (it only validates, serializes, and runs simulations — it never
writes your financial data to disk). Create or **upload** a plan YAML file, edit
it via forms (with a read-only YAML preview tab), **download** it to keep a copy
on disk, and hit **Run simulation** for the success probability, percentile
tables, and interactive versions of the three charts with a today's-dollars /
nominal toggle. Downloaded files are byte-compatible with the CLI, so a plan
saved from the browser runs unchanged via `retirement-sim my_plan.yaml`. The
example files in `configs/` are a good starting point to upload.

For frontend development, `npm run dev` inside `frontend/` starts a Vite dev
server with hot reload that proxies `/api` to the Python server.

### Running in a container

The app ships as a single self-contained image: a multi-stage `Dockerfile`
builds the React frontend and serves it, alongside the JSON API, from one
stateless FastAPI process (no database, no volumes).

```bash
docker build -t retirement-sim .
docker run --rm -p 8000:8000 retirement-sim   # open http://localhost:8000
```

The server binds `0.0.0.0` and listens on `$PORT` (default `8000`), so hosts
that inject a port — e.g. Azure App Service — work without changes:

```bash
docker run --rm -e PORT=9000 -p 9000:9000 retirement-sim
```

## Configuration

See `configs/example_income_goal.yaml` (fully commented) and
`configs/example_target_amount.yaml`. The pieces:

| Section | What it does |
|---|---|
| `person` | `current_age`, `retirement_age`, `death_age` (planning horizon) |
| `accounts` | One entry per account: `name`, `type` (label only — taxes are not modeled), starting `balance`, and either a fixed `allocation` or a `glide_path` |
| `contributions` | Annual dollar amounts per account (multiply monthly figures by 12), in today's dollars. `index_to_inflation` grows them with each path's simulated inflation; `extra_annual_increase` compounds on top. Instead of `annual_amount` you can give `salary` + `savings_rate` (a fraction, e.g. `0.15`), which contributes that share of salary and defaults to Fidelity's inflation + 1.5% real salary growth. `changes` schedules any number of resets at future ages (e.g. a CoastFI downshift) |
| `goal` | Either `retirement_income` with `monthly_income_today` (today's dollars, sustained from retirement to death) or `target_amount` with `amount` and `basis: real\|nominal` (reached by retirement age) |
| `social_security` | Optional: `claiming_age` plus either `monthly_benefit_today` (given directly) or `pia_monthly` (your benefit at full retirement age — the sim applies SSA early-reduction / delayed-credit factors, with optional `full_retirement_age`, default 67). The benefit is COLA'd along each path's inflation and offsets withdrawals |
| `market` | Optional overrides of the default capital-market assumptions (deep-merged onto `retirement_sim/defaults.yaml`) |
| `fees` | Optional `drag_bps` (annual expense ratio in basis points) applied to every account; an account's own `fee_drag_bps` overrides it |
| `simulation` | `n_sims` (default 10,000) and optional `seed` for reproducibility |
| `output` | Chart directory, `charts: true\|false`, `chart_dollars: real\|nominal`, `show: true\|false` (interactive windows) |

Success is defined per goal: for `retirement_income`, the fraction of paths that
never deplete before `death_age`; for `target_amount`, the fraction of paths whose
retirement-date balance meets the target.

### Field options

Values accepted by the enum-like config fields (anything else is rejected at load
with an error listing the valid choices):

| Field | Options | Notes |
|---|---|---|
| `accounts[].type` | `401k`, `roth_401k`, `403b`, `trad_ira`, `roth_ira`, `brokerage`, `hsa`, `cash`, `other` | Labels only for now — taxes are not modeled, so all types grow and are withdrawn identically |
| `accounts[].allocation` / `glide_path` asset classes | `stocks`, `bonds`, `cash` by default | The set comes from `market.asset_classes`; add your own class under `market:` (with correlation pairs) and it becomes valid here |
| `goal.type` | `retirement_income`, `target_amount` | Exactly one goal per config |
| `goal.basis` | `real` (default), `nominal` | `target_amount` only: compare the retirement balance in today's dollars or future dollars |
| `output.chart_dollars` | `real` (default), `nominal` | Which dollars the charts plot |
| `contributions[].index_to_inflation`, `output.charts`, `output.show` | `true` / `false` | Booleans, not enums, listed here for completeness |

## Default market assumptions (nominal, annual)

| Series | Mean | Vol |
|---|---|---|
| stocks | 9.5% | 16% |
| bonds | 4.5% | 6% |
| cash | 3.0% | 1.5% |
| inflation | 2.5% | 1.5% |

Correlations: stocks–bonds 0.10, stocks–inflation −0.20, bonds–inflation −0.30,
cash–inflation 0.50, bonds–cash 0.30. Override any of these (or add new asset
classes plus their correlation pairs) under `market:` in your config.

## Methodology

- **Annual time steps**, fully vectorized over paths (10,000 paths × 60 years runs
  in well under a second).
- **Returns and inflation are drawn jointly** from a multivariate normal in
  log(1 + r) space (lognormal growth factors, so returns can never fall below
  −100%). Log-space parameters are moment-matched so the sampled arithmetic
  mean/vol equal the configured numbers. Drawing inflation jointly with returns
  means "high inflation + weak bonds" failure sequences appear naturally.
- **Three return models**, selected with `market.method`:
  - `parametric` (default) — the lognormal draws described above.
  - `student_t` — same log-space moments, but the shocks are multivariate
    Student-t (`market.student_t.df`, default 6): crashes and booms are more
    extreme, and assets crash together (tail dependence). Arithmetic mean/vol
    are matched approximately rather than exactly in this mode.
  - `bootstrap` — resamples `market.bootstrap.block_years`-long (default 5)
    blocks of actual US history 1928–2025, whole years taken jointly, so fat
    tails, cross-correlations, *and* multi-year sequences (Depression, 1970s
    stagflation, 2008) come straight from the record. By default the configured
    mean/vol/correlations are ignored and the raw historical means apply — which
    are richer than the packaged defaults (~11.7% nominal stocks vs 9.5%), so
    plain bootstrap runs skew more optimistic than the other models. Set
    `market.bootstrap.recenter: true` to shift each series so its mean matches
    the configured `market.*.mean` while keeping the historical volatility,
    co-movement, and sequence risk — making the three models comparable on the
    mean assumption (vols stay historical). Consider `simulation.n_sims` of
    25,000+ for smoother tails. Data: S&P 500 (incl. dividends), 10-year
    Treasury, and 3-month T-bill returns from A. Damodaran's NYU Stern dataset
    plus CPI-U December-over-December inflation (FRED `CPIAUCNS`), bundled as
    `retirement_sim/historical_returns.csv` with provenance in its header —
    refresh by re-deriving those columns for new years. A custom dataset can be
    supplied via `market.bootstrap.data` (CSV: `year,<one column per configured
    asset class>,inflation`, decimals, consecutive years).
- **Nominal accounting, real reporting.** Each path carries its own cumulative
  inflation index; today's-dollar inputs (spending, contributions, Social
  Security) are inflated along the path, and results are deflated back for the
  today's-dollar columns and charts.
- **Yearly order of operations** (beginning-of-year convention): cash flows
  (contributions before retirement, withdrawals net of Social Security after),
  then growth at that year's drawn returns. Taking withdrawals before growth is
  the conservative choice and is what makes sequence-of-returns risk bite.
- **Withdrawals are pooled** across accounts proportionally to balance.
- **Glide paths** are piecewise-linearly interpolated between age points and held
  flat beyond the ends.

## Limitations (deliberate, for now)

- **No taxes**: account types are labels; everything grows and is withdrawn as one
  pool. Express your income goal as a gross (pre-tax) number. The withdrawal logic
  is isolated in one function so tax-aware ordering can be added later.
- **i.i.d. annual draws in the parametric modes**: with `parametric` or
  `student_t`, inflation and returns have no year-to-year persistence (no
  1970s-style multi-year inflation regimes) and no mean reversion. Use
  `market.method: bootstrap` when those sequences matter.
- **No pensions or annuities.**
- The 4%-rule benchmark test (`tests/test_end_to_end.py`) checks the engine lands
  in the 80–95%-ish success range the literature reports for a 60/40 portfolio
  over a 30-year retirement.

## Development

```bash
uv run pytest
```

The test suite includes closed-form zero-volatility checks (compound growth,
depletion age, inflation indexing), statistical tests that sampled moments and
correlations match the config, and end-to-end runs of both example configs.

## Layout

```
retirement_sim/
  cli.py         command-line entry point
  config.py      YAML schema, defaults merge, validation
  defaults.yaml  default capital-market assumptions
  market.py      correlated return/inflation path generation
  allocation.py  glide-path resolution
  simulate.py    vectorized Monte Carlo engine
  results.py     success probability, percentiles, depletion stats
  report.py      terminal summary and PNG charts
  web.py         stateless FastAPI server for the web UI (validate/serialize/simulate)
frontend/        React web UI (Vite + TypeScript + Recharts)
configs/         example plan configs
tests/           unit, statistical, and end-to-end tests
```
