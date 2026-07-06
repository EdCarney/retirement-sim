"""Resolve an account's asset allocation for each simulated age."""

from __future__ import annotations

import numpy as np

from .config import Account


def resolve_allocations(account: Account, ages: np.ndarray, asset_names: list[str]) -> np.ndarray:
    """Allocation weights for each age, shape (len(ages), n_assets).

    Fixed-allocation accounts get a constant matrix. Glide paths are
    piecewise-linearly interpolated between the configured age points and
    held flat before the first / after the last point. Rows are
    renormalized to absorb interpolation rounding.
    """
    if account.allocation is not None:
        weights = np.array([account.allocation.get(name, 0.0) for name in asset_names])
        return np.tile(weights, (len(ages), 1))

    point_ages = [point.age for point in account.glide_path]
    weights = np.column_stack(
        [
            np.interp(ages, point_ages, [point.allocation.get(name, 0.0) for point in account.glide_path])
            for name in asset_names
        ]
    )
    return weights / weights.sum(axis=1, keepdims=True)
