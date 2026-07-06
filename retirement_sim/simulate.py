"""Vectorized Monte Carlo engine.

Everything is simulated in nominal dollars; each path carries its own
cumulative inflation index so today's-dollar amounts (contributions,
spending, Social Security) can be inflated along the path and results can
be deflated back to today's dollars for reporting.

Yearly order of operations at age ``a`` (beginning-of-year convention —
withdrawals happen before growth, the conservative choice that captures
sequence-of-returns risk):
    1. cash flows: contributions while a < retirement_age, withdrawals
       (net of Social Security) from retirement_age on
    2. growth at this year's drawn asset returns
    3. cumulative inflation index update

Contributions therefore occur at ages [current_age, retirement_age) and
withdrawals at [retirement_age, death_age).
"""

from __future__ import annotations

import numpy as np

from .allocation import resolve_allocations
from .config import GOAL_RETIREMENT_INCOME, ContributionStream, PlanConfig
from .market import generate_paths
from .results import SimulationResults


def contribution_amounts(stream: ContributionStream, age: int, cum_inflation: np.ndarray) -> np.ndarray:
    """Nominal contribution per path for this stream at ``age``."""
    phase = stream.phase_at(age)
    years_in_phase = age - phase.start_age
    base = phase.annual_amount * (1.0 + phase.extra_annual_increase) ** years_in_phase
    if phase.index_to_inflation:
        return base * cum_inflation
    return np.full_like(cum_inflation, base)


def apply_withdrawal(balances: np.ndarray, amounts: np.ndarray) -> np.ndarray:
    """Withdraw ``amounts`` (per path) proportionally across accounts, in place.

    This is the single hook a future tax-aware withdrawal policy would
    replace (e.g. taxable first, then traditional, then Roth).

    Returns a boolean mask of paths whose pooled balance could not cover
    the withdrawal; their balances are zeroed.
    """
    totals = balances.sum(axis=1)
    shortfall = totals < amounts - 1e-9
    fraction = np.divide(amounts, totals, out=np.ones_like(totals), where=totals > 0)
    balances *= np.clip(1.0 - fraction, 0.0, 1.0)[:, None]
    balances[shortfall] = 0.0
    return shortfall


def run_simulation(
    config: PlanConfig, n_sims: int | None = None, seed: int | None = None
) -> SimulationResults:
    """Run the Monte Carlo simulation. ``n_sims``/``seed`` override config."""
    person = config.person
    goal = config.goal
    n_sims = n_sims if n_sims is not None else config.simulation.n_sims
    seed = seed if seed is not None else config.simulation.seed

    # Income goals simulate through the full retirement; target-amount
    # goals only need the accumulation phase.
    horizon_age = person.death_age if goal.type == GOAL_RETIREMENT_INCOME else person.retirement_age
    n_years = horizon_age - person.current_age
    ages = np.arange(person.current_age, horizon_age + 1)

    rng = np.random.default_rng(seed)
    asset_returns, inflation = generate_paths(config.market, n_sims, n_years, rng)
    asset_names = config.market.asset_names
    weights = [resolve_allocations(account, ages[:-1], asset_names) for account in config.accounts]

    account_index = {account.name: i for i, account in enumerate(config.accounts)}
    balances = np.tile([float(a.balance) for a in config.accounts], (n_sims, 1))
    # Per-account annual fee multiplier: an expense ratio charged on assets,
    # so growth is scaled by (1 - fee) each year.
    fee_keep = np.array([1.0 - config.fees.account_fee(a) for a in config.accounts])
    cum_inflation = np.ones(n_sims)

    history = np.empty((n_sims, n_years + 1))
    account_history = np.empty((n_sims, n_years + 1, len(config.accounts)))
    cum_inflation_history = np.empty((n_sims, n_years + 1))
    depletion_age = np.full(n_sims, np.nan)

    history[:, 0] = balances.sum(axis=1)
    account_history[:, 0] = balances
    cum_inflation_history[:, 0] = 1.0

    ss = config.social_security
    for t in range(n_years):
        age = person.current_age + t

        if age < person.retirement_age:
            for stream in config.contributions:
                balances[:, account_index[stream.account]] += contribution_amounts(stream, age, cum_inflation)
        elif goal.type == GOAL_RETIREMENT_INCOME:
            spending = goal.monthly_income_today * 12.0 * cum_inflation
            if ss is not None and age >= ss.claiming_age:
                spending = np.maximum(spending - ss.monthly_benefit_today * 12.0 * cum_inflation, 0.0)
            newly_depleted = apply_withdrawal(balances, spending)
            depletion_age[newly_depleted & np.isnan(depletion_age)] = age

        for j in range(len(config.accounts)):
            balances[:, j] *= (1.0 + asset_returns[:, t, :] @ weights[j][t]) * fee_keep[j]

        cum_inflation = cum_inflation * (1.0 + inflation[:, t])

        history[:, t + 1] = balances.sum(axis=1)
        account_history[:, t + 1] = balances
        cum_inflation_history[:, t + 1] = cum_inflation

    return SimulationResults(
        config=config,
        n_sims=n_sims,
        seed=seed,
        ages=ages,
        history=history,
        account_history=account_history,
        cum_inflation=cum_inflation_history,
        depletion_age=depletion_age,
        retirement_index=person.retirement_age - person.current_age,
    )
