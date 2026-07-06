# Aligning our simulator with Fidelity's retirement methodology

**Purpose:** compare our Monte Carlo engine against Fidelity's published
retirement-analysis methodology and lay out a prioritized, concrete plan of
changes to make ours more faithful to it.

**Source:** Fidelity, *Retirement Analysis Methodology*
(<https://www.fidelity.com/go/guidance/retirement-methodology>), fetched
2026-07-06. A condensed capture of the relevant points is in the
[Appendix](#appendix-fidelity-methodology-as-captured).

**Caveats**
- This is an *engineering* gap analysis of modeling methodology, not financial
  advice.
- Fidelity's doc leaves some things undisclosed (exact simulation count, exact
  return distribution family, the Retirement Score band cutoffs). Where a
  proposal leans on numbers not in the doc, it is flagged.
- **Taxes and RMDs are a deliberate non-goal of this project** (account `type`
  is a label only; taxes are intentionally unmodeled). Fidelity models both;
  this plan keeps them out of scope and explains where the seam is if that ever
  changes. See [Non-goals](#non-goals-deliberately-out-of-scope).

---

## 1. Side-by-side summary

| Dimension | Fidelity | Ours (today) | Gap? |
|---|---|---|---|
| Return source | Historical index returns (S&P 500 / DJ US TMI, EAFE/ACWI, Agg bonds, T-bills) | Parametric multivariate **lognormal**, moment-matched to configured arithmetic mean/vol (`market.py`, `config.py:SeriesParams.log_params`) | **Yes** — parametric vs empirical |
| Distribution shape | Empirical → fat tails, skew, real crashes | Symmetric in log space; thin tails | **Yes** |
| Serial correlation | Present (historical sequences) | i.i.d. across years (`generate_paths`) | **Yes** |
| Cross-correlation | Asset + inflation correlations | Modeled via covariance in log space (`correlation_matrix`) | No — parity |
| Inflation | General **2.5%**; health-care on a declining schedule (**4.9% → 2.5%**) | Single i.i.d. normal series, default mean 2.5% / vol 1.5% (`defaults.yaml`) | **Partial** — no persistence, no health-care bucket |
| Headline metric | Outcome at **90% confidence** (10th-pctile market), conservative | **Success probability** across all paths (`results.success_probability`) | **Yes** — add confidence-outcome framing |
| Score / bands | Retirement Score with color bands (cutoffs not in doc) | Frontend colors prob ok/warn/bad; no formal score | **Partial** |
| Longevity | **Planning age = 25% survival** (75th pctile, RP-2014 healthy annuitant) | Single deterministic `death_age` | **Yes** — deterministic, no guidance |
| Social Security | Estimated from earnings + claiming age; deferral credits; 2.5% COLA | User supplies benefit; COLA'd by each path's **simulated** inflation (`simulate.py`) | **Partial** — ours COLA is arguably better; no benefit estimation |
| Salary / contributions | Salary grows inflation **+1.5%**; contributions % of salary; IRS limits enforced | Today's-dollar amounts with `index_to_inflation` + `extra_annual_increase`; no limit checks | **Partial** — expressible, not defaulted |
| Fees | Index-based, no fees (notes real returns are lower) | None | **Yes** — easy realism win |
| Taxes / RMDs | Federal ordinary + cap gains; RMDs from 73/75; penalties; tax-aware withdrawal order | **Not modeled (by design)**; proportional withdrawal (`apply_withdrawal`) | **Non-goal** |
| Withdrawal timing | Not isolated | Beginning-of-year (pre-growth) → captures sequence risk | No gap — ours is a strength |
| # simulations | Undisclosed | 10,000 default | No material gap |

---

## 2. Prioritized plan

Effort = rough size; Risk = chance of destabilizing existing behavior/tests.

### Tier 1 — highest fidelity-per-effort

#### 1.1 Fat-tailed / historically-realistic returns
- **Why:** the single biggest divergence. i.i.d. lognormal understates crash
  tails and, combined with independence, misstates long-horizon dispersion.
- **What Fidelity does:** replays historical index returns.
- **Two options (can ship incrementally):**
  - **(a) Quick win — Student-t innovations.** Replace the standard-normal `z`
    in `generate_paths` with a multivariate Student-t (e.g. ν≈5–8), rescaled to
    preserve the configured vol. Fatter tails, no external data needed.
  - **(b) Fuller — block bootstrap.** Add a `market.method: bootstrap` mode that
    samples overlapping **multi-year blocks** (e.g. 3–5 yr) from a bundled
    historical returns+inflation dataset. This captures fat tails *and* serial
    correlation/sequence risk in one move — closest to Fidelity.
- **Files:** `market.py` (strategy switch), `config.py` (`market.method`,
  `market.tail`/`block_years`, optional data path), a bundled
  `historical_returns.csv`, `defaults.yaml`.
- **Effort:** (a) S, (b) M–L (data sourcing/licensing is the main cost).
- **Risk:** M — changes the core draw; keep `parametric` the default so existing
  configs/tests are unaffected, add tests for the new modes.

#### 1.2 Inflation persistence (+ optional health-care spend bucket)
- **Why:** i.i.d. annual inflation is unrealistic (inflation is highly
  autocorrelated); and retiree spending inflates faster than headline CPI.
- **What Fidelity does:** 2.5% general; health-care schedule 4.9% → 2.5%.
- **Proposed:**
  - Add an **AR(1)** option for the inflation series (persistence ρ) so shocks
    carry across years.
  - Optionally split the income goal into a `health_care` fraction with its own
    (higher, decaying) inflation schedule, layered on the base spend.
- **Files:** `config.py` (`market.inflation.persistence`; goal `health_care`
  block), `market.py` (AR(1) path), `simulate.py` (spending assembly around
  line 98).
- **Effort:** M. **Risk:** L–M (guarded behind new optional fields).

#### 1.3 Confidence-level & score reporting
- **Why:** match Fidelity's conservative *90%-confidence* headline and give a
  banded, at-a-glance read.
- **Proposed (reporting only — no engine change):**
  - Report the **outcome at the 90% confidence level** = the 10th-percentile
    path's sustainable income / ending balance, alongside our existing success
    probability. (We already compute percentile bands in `results.py`.)
  - Add a banded "score" derived from success probability with **configurable**
    thresholds (defaults suggested, e.g. ≥90 green / 80–90 yellow / <80 red).
    Fidelity's exact Retirement Score cutoffs are **not in the doc**, so treat
    thresholds as configurable, not as literal Fidelity numbers.
- **Files:** `results.py` (`confidence_outcome(level=0.90)`, `score_band()`),
  `report.py` (summary line), frontend headline (already color-codes prob —
  align thresholds).
- **Effort:** S. **Risk:** L.

#### 1.4 Fee drag
- **Why:** Fidelity's index simulations assume no fees but explicitly note real
  returns are reduced by them; a small drag markedly changes long-horizon tails.
- **Proposed:** optional `fee_drag_bps` (global and/or per-account), subtracted
  from the annual return in the growth step.
- **Files:** `config.py` (`fee_drag_bps`), `simulate.py` (growth step ~line 105).
- **Effort:** S. **Risk:** L.

### Tier 2 — meaningful, larger or more optional

#### 2.1 Longevity: planning age + optional stochastic mortality
- **What Fidelity does:** planning age = age with 25% survival probability
  (RP-2014 healthy annuitant), a conservative single horizon.
- **Proposed:**
  - **Guidance/helper** to set `death_age` to the 25%-survival planning age from
    a bundled mortality table (documentation + a small helper/CLI flag).
  - **Optional** `longevity: stochastic` mode that draws each path's death age
    from the mortality table, so success reflects market **and** longevity risk.
    Note this changes the semantics of "success" and needs report copy updates.
- **Files:** `config.py` (`person.planning_basis` / `longevity`), `simulate.py`
  (per-path horizon), `results.py`/`report.py` (semantics), bundled mortality CSV.
- **Effort:** M–L. **Risk:** M (variable horizon touches the vectorized core).

#### 2.2 Salary-linked contributions + IRS-limit awareness
- **What Fidelity does:** salary grows inflation **+1.5%**; contributions as % of
  salary; enforces IRS limits.
- **Reality check:** we can *already* express inflation+1.5% growth today via
  `index_to_inflation: true` + `extra_annual_increase: 0.015`. Gaps are (a) it's
  not the default/among documented presets, (b) no % -of-salary mode, (c) no
  limit warnings.
- **Proposed:** document the mapping; optionally add a `salary` block with a
  growth rate and percent-of-salary contributions; add a **soft warning** when
  `annual_amount` exceeds the current IRS limit for the account type.
- **Files:** docs first; then `config.py` (`salary`, limit table + warning),
  `simulate.py` (contribution assembly).
- **Effort:** S (docs/warnings) → M (salary mode). **Risk:** L.

#### 2.3 Social Security benefit estimation & deferral credits
- **What Fidelity does:** estimates PIA from earnings and applies early-reduction
  / delayed-retirement credits by claiming age.
- **Ours:** user supplies the benefit; we COLA it by each path's **simulated**
  inflation — a genuine strength worth keeping and highlighting.
- **Proposed (low priority):** optional helper to derive the benefit from a PIA
  and claiming age (apply the standard reduction/credit schedule), keeping the
  user-supplied value as the default.
- **Files:** `config.py` (optional `social_security.pia` + claiming logic).
- **Effort:** M. **Risk:** L.

---

## 3. Non-goals (deliberately out of scope)

Kept out on purpose, consistent with the project's design (account `type` is a
label; taxes are unmodeled):

- **Federal / capital-gains taxes**, qualified-dividend treatment, taxable-account
  turnover.
- **RMDs** (age 73/75) and early-withdrawal penalties — largely moot without tax
  modeling and with spending-driven withdrawals.
- **Tax-aware withdrawal sequencing** (taxable → traditional → Roth).

If this ever changes, the single seam is `apply_withdrawal` in `simulate.py`
(its docstring already calls this out) plus a spending gross-up for taxes.

---

## 4. Suggested sequencing

1. **1.4 Fee drag** and **1.3 Confidence/score reporting** — small, high-signal,
   low-risk; ship first.
2. **1.1(a) Student-t tails** — small change, immediately more realistic tails.
3. **1.2 Inflation persistence** — medium, removes an obvious unrealism.
4. **1.1(b) Block bootstrap** — the flagship change; do once historical data is
   sourced. Bump default `n_sims` (e.g. 25k–50k) for smoother tails here.
5. **2.1 Longevity**, then **2.2 / 2.3** as appetite allows.

Throughout: keep `parametric` returns and deterministic `death_age` as the
defaults so existing configs and tests remain valid; gate every new behavior
behind an opt-in field and add targeted tests.

---

## Appendix: Fidelity methodology as captured

Condensed from the source page (2026-07-06); some items are undisclosed there.

- **Asset benchmarks:** domestic equity (S&P 500 → DJ US Total Market), foreign
  equity (S&P 500 → MSCI EAFE → MSCI ACWI ex-US), bonds (intermediate → Bloomberg
  US Aggregate), short-term (30-day T-bills). Uses historical returns, volatility,
  and correlations, reviewed annually. Distribution family not explicitly stated;
  mean reversion / forward-looking adjustments not mentioned.
- **Confidence:** default **90%** ("significantly below average" = bottom 10% of
  scenarios); also 75% ("below average") and 50% ("average"). Defaults to 90% to
  be conservative. Exact scenario count undisclosed.
- **Retirement Score / success:** core criterion is whether projected assets cover
  expenses to the planning age at the chosen confidence; explicit score-band
  cutoffs **not disclosed** in this doc.
- **Inflation:** general **2.5%**; health-care starts ~**4.9%** and declines toward
  general over time. Social Security COLA assumed **2.5%**.
- **Salary growth:** inflation **+1.5%** (≈4.0%). Contributions assumed to stop at
  retirement; IRS limits (2026: $32,500 age 50+, $35,750 ages 60–63) applied.
- **Planning age (longevity):** age with an estimated **25% survival** probability
  (75% chance of dying before it), from the Society of Actuaries **RP-2014**
  healthy-annuitant table; female life expectancy used as a conservative default.
- **Taxes:** federal ordinary **10–37%**; long-term cap gains **0/15/20%**;
  qualified dividends at cap-gains rates; **10%** annual taxable-account turnover;
  dividend yields 2% domestic / 3% foreign.
- **RMDs:** from age **73** (75 if born 1960+), Uniform Lifetime Table; 10% early
  penalty before 59½ (with the age-55 separation exception).
- **Fees:** index simulations assume no management/servicing fees, but the doc
  notes real returns are reduced by actual fund fees.
- **Withdrawal order (for annuity purchases):** tax-deferred annuity → tax-deferred
  assets → after-tax taxable proceeds → tax-exempt. Sequence-of-returns risk not
  isolated.
