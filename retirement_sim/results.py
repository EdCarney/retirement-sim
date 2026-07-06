"""Simulation results container and derived metrics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import GOAL_RETIREMENT_INCOME, GOAL_TARGET_AMOUNT, PlanConfig


@dataclass(frozen=True)
class SimulationResults:
    config: PlanConfig
    n_sims: int
    seed: int | None
    ages: np.ndarray                # (n_years + 1,) age at each recorded point
    history: np.ndarray             # (n_sims, n_years + 1) nominal total balance
    account_history: np.ndarray     # (n_sims, n_years + 1, n_accounts) nominal
    cum_inflation: np.ndarray       # (n_sims, n_years + 1), column 0 == 1.0
    depletion_age: np.ndarray       # (n_sims,) age portfolio ran dry, NaN if never
    retirement_index: int           # column index of the retirement-age snapshot

    def real_history(self) -> np.ndarray:
        """Balance history deflated to today's dollars, per path."""
        return self.history / self.cum_inflation

    def balances_at(self, index: int, real: bool = True) -> np.ndarray:
        balances = self.history[:, index]
        if real:
            return balances / self.cum_inflation[:, index]
        return balances

    def success_probability(self) -> float:
        goal = self.config.goal
        if goal.type == GOAL_RETIREMENT_INCOME:
            return float(np.mean(np.isnan(self.depletion_age)))
        balances = self.balances_at(self.retirement_index, real=goal.basis == "real")
        return float(np.mean(balances >= goal.amount))

    def percentile_bands(self, percentiles: list[float], real: bool = True) -> np.ndarray:
        """Per-year balance percentiles, shape (len(percentiles), n_years + 1)."""
        history = self.real_history() if real else self.history
        return np.percentile(history, percentiles, axis=0)

    def failure_fraction_by_year(self) -> np.ndarray:
        """Fraction of paths already depleted at each recorded age."""
        depletion = self.depletion_age[:, None]
        return np.mean(~np.isnan(depletion) & (depletion <= self.ages[None, :]), axis=0)

    def median_depletion_age(self) -> float | None:
        """Median age at which failing paths ran out of money (None if no failures)."""
        failed = self.depletion_age[~np.isnan(self.depletion_age)]
        if failed.size == 0:
            return None
        return float(np.median(failed))
