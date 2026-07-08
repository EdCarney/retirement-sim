"""Maximum sustainable withdrawal ("die with zero") analysis.

Answers the inverse of the main simulation: given a lump sum at retirement,
what is the largest constant, inflation-adjusted (today's-dollars) withdrawal
that draws the account down to roughly zero over the retirement horizon?

The drawdown reuses the primary engine's conventions exactly (beginning-of-year
withdraw-then-grow, proportional multi-account withdrawal, per-account fees and
glide paths -- see ``simulate.py``). Because the ending balance is monotonically
non-increasing in the withdrawal amount, the max sustainable withdrawal is found
per path by a vectorized bisection: everything is simulated in nominal dollars
with the withdrawal indexed to inflation, and the solved amount is therefore
already expressed in today's dollars.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .allocation import resolve_allocations
from .config import GOAL_RETIREMENT_INCOME, PlanConfig
from .market import generate_paths
from .report import PERCENTILES
from .results import SimulationResults
from .simulate import apply_withdrawal

# Bisection iterations. Each halves the bracket, so ~40 gives relative
# precision far below a rounding cent while the per-year recursion (which
# dominates cost) is what we keep bounded via the path count.
_BISECT_ITERS = 40

# Cap on paths drawn for the drawdown search when embedding this in the main
# results payload; withdrawal percentiles are stable well below the primary
# simulation's path count, and this keeps ``/api/simulate`` responsive.
_MAX_SOLVER_SIMS = 4000

# The three market scenarios shown in the frontend's scenario chart, worst
# first. The percentiles double as the balance percentiles at retirement used
# as starting lump sums. Labels live in the frontend (palette.ts); the payload
# carries only the percentile so the UI stays the single source of truth.
_SCENARIO_PERCENTILES = (10, 25, 50)


def max_sustainable_withdrawal(
    config: PlanConfig,
    start_balance: float,
    account_shares: np.ndarray,
    n_years: int,
    n_sims: int,
    seed: int | None = None,
) -> np.ndarray:
    """Per-path max constant-real annual withdrawal that depletes ``start_balance``.

    ``account_shares`` (one weight per account, summing to 1) splits the lump
    sum across accounts so each keeps its own allocation/glide path. Returns an
    array of length equal to the drawn path count (``market.method == 'all'``
    triples ``n_sims``) holding the today's-dollars annual withdrawal.
    """
    rng = np.random.default_rng(seed)
    asset_returns, inflation = generate_paths(config.market, n_sims, n_years, rng)
    n_paths = asset_returns.shape[0]

    ages = np.arange(config.person.retirement_age, config.person.death_age)
    asset_names = config.market.asset_names
    weights = [resolve_allocations(account, ages, asset_names) for account in config.accounts]
    fee_keep = np.array([1.0 - config.fees.account_fee(a) for a in config.accounts])
    start_split = np.tile(account_shares * start_balance, (n_paths, 1))

    def ending_balance(withdrawal: np.ndarray) -> np.ndarray:
        balances = start_split.copy()
        cum_inflation = np.ones(n_paths)
        for t in range(n_years):
            apply_withdrawal(balances, withdrawal * cum_inflation)
            for j in range(len(config.accounts)):
                balances[:, j] *= (1.0 + asset_returns[:, t, :] @ weights[j][t]) * fee_keep[j]
            cum_inflation = cum_inflation * (1.0 + inflation[:, t])
        return balances.sum(axis=1)

    # Bracket: at W=0 the account only grows (survives); withdrawing the whole
    # balance in year 0 depletes it immediately (ends at zero).
    lo = np.zeros(n_paths)
    hi = np.full(n_paths, float(start_balance))
    for _ in range(_BISECT_ITERS):
        mid = 0.5 * (lo + hi)
        survived = ending_balance(mid) > 0.0
        lo = np.where(survived, mid, lo)
        hi = np.where(survived, hi, mid)
    return lo


def scenario_withdrawals(
    results: SimulationResults, n_sims: int | None = None, seed: int | None = None
) -> dict[str, Any] | None:
    """Max-withdrawal percentiles for each market scenario at retirement.

    For each of the significantly-below / below / average market balances at
    retirement (p10/p25/p50, today's dollars), solve the die-with-zero
    withdrawal distribution and report its 90..10th percentiles. Returns
    ``None`` for non-income goals (no retirement drawdown horizon).
    """
    config = results.config
    person = config.person
    if config.goal.type != GOAL_RETIREMENT_INCOME:
        return None
    n_years = person.death_age - person.retirement_age
    if n_years <= 0:
        return None

    real_balances = results.balances_at(results.retirement_index, real=True)
    # Split each lump sum across accounts by the median composition at
    # retirement, so accounts keep their distinct glide paths in the drawdown.
    composition = np.median(results.account_history[:, results.retirement_index, :], axis=0)
    total = composition.sum()
    shares = composition / total if total > 0 else np.full(len(composition), 1.0 / len(composition))

    solver_sims = n_sims if n_sims is not None else min(results.n_sims, _MAX_SOLVER_SIMS)
    solver_seed = seed if seed is not None else (None if results.seed is None else results.seed + 1)

    scenarios = []
    for scenario_p in _SCENARIO_PERCENTILES:
        start_balance = float(np.percentile(real_balances, scenario_p))
        withdrawals = max_sustainable_withdrawal(
            config, start_balance, shares, n_years, solver_sims, solver_seed
        )
        rows = []
        for p in reversed(PERCENTILES):  # 90th (optimistic) .. 10th (conservative)
            annual = float(np.percentile(withdrawals, p))
            rows.append(
                {
                    "percentile": p,
                    "monthly": annual / 12.0,
                    "annual": annual,
                    "rate": annual / start_balance if start_balance > 0 else 0.0,
                }
            )
        scenarios.append({"percentile": scenario_p, "start_balance": start_balance, "rows": rows})

    return {"n_years": n_years, "scenarios": scenarios}
