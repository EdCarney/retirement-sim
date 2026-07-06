import numpy as np

from retirement_sim.allocation import resolve_allocations
from retirement_sim.config import Account, GlidePathPoint

ASSETS = ["stocks", "bonds", "cash"]


def test_fixed_allocation_is_constant():
    account = Account(name="a", type="401k", balance=1.0, allocation={"stocks": 0.7, "bonds": 0.3})
    weights = resolve_allocations(account, np.array([40, 41, 42]), ASSETS)
    assert weights.shape == (3, 3)
    np.testing.assert_allclose(weights, [[0.7, 0.3, 0.0]] * 3)


def _glide_account():
    return Account(
        name="g",
        type="brokerage",
        balance=1.0,
        glide_path=(
            GlidePathPoint(age=40, allocation={"stocks": 0.9, "bonds": 0.1}),
            GlidePathPoint(age=60, allocation={"stocks": 0.5, "bonds": 0.4, "cash": 0.1}),
        ),
    )


def test_glide_path_hits_configured_points():
    weights = resolve_allocations(_glide_account(), np.array([40, 60]), ASSETS)
    np.testing.assert_allclose(weights[0], [0.9, 0.1, 0.0])
    np.testing.assert_allclose(weights[1], [0.5, 0.4, 0.1])


def test_glide_path_interpolates_between_points():
    weights = resolve_allocations(_glide_account(), np.array([50]), ASSETS)
    np.testing.assert_allclose(weights[0], [0.7, 0.25, 0.05])


def test_glide_path_flat_beyond_endpoints():
    weights = resolve_allocations(_glide_account(), np.array([30, 80]), ASSETS)
    np.testing.assert_allclose(weights[0], [0.9, 0.1, 0.0])
    np.testing.assert_allclose(weights[1], [0.5, 0.4, 0.1])


def test_rows_always_sum_to_one():
    ages = np.arange(30, 90)
    weights = resolve_allocations(_glide_account(), ages, ASSETS)
    np.testing.assert_allclose(weights.sum(axis=1), 1.0, rtol=1e-12)
