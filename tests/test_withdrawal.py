import numpy as np

from retirement_sim.config import build_config
from retirement_sim.simulate import run_simulation
from retirement_sim.withdrawal import max_sustainable_withdrawal, scenario_withdrawals


def _income_config(raw_config, deterministic_market):
    """A retired, single-account, deterministic-6%, zero-inflation plan."""
    raw_config["market"] = deterministic_market
    raw_config["person"] = {"current_age": 65, "retirement_age": 65, "death_age": 95}
    raw_config["accounts"][0]["allocation"] = {"stocks": 1.0}
    raw_config["goal"] = {"type": "retirement_income", "monthly_income_today": 1}
    return build_config(raw_config)


def test_die_with_zero_matches_annuity_closed_form(raw_config, deterministic_market):
    config = _income_config(raw_config, deterministic_market)
    start_balance = 500_000.0
    n_years = 30
    g = 1.06  # deterministic stocks return, no inflation, no fees

    withdrawals = max_sustainable_withdrawal(
        config, start_balance, np.array([1.0]), n_years, n_sims=25, seed=1
    )

    # Withdraw-then-grow annuity: the payment W with B_N == 0 solves
    # B0*g^N == W * (g^1 + ... + g^N), i.e. W = B0 * g^(N-1) * (g-1) / (g^N - 1).
    expected = start_balance * g ** (n_years - 1) * (g - 1) / (g**n_years - 1)
    np.testing.assert_allclose(withdrawals, expected, rtol=1e-5)


def test_withdrawing_the_solved_amount_lands_near_zero(raw_config, deterministic_market):
    config = _income_config(raw_config, deterministic_market)
    start_balance, n_years, g = 500_000.0, 30, 1.06

    w = float(max_sustainable_withdrawal(
        config, start_balance, np.array([1.0]), n_years, n_sims=5, seed=1
    )[0])

    # Independently replay the withdraw-then-grow recursion; it should end ~0.
    balance = start_balance
    for _ in range(n_years):
        balance = (balance - w) * g
    assert abs(balance) < start_balance * 1e-4
    assert balance >= -1.0  # solver returns the largest sustainable W (never overshoots)


def test_scenario_withdrawals_shape_and_ordering(raw_config, deterministic_market):
    # Give the accumulation phase some runway so the retirement balance is real.
    raw_config["person"] = {"current_age": 60, "retirement_age": 65, "death_age": 95}
    raw_config["market"] = deterministic_market
    raw_config["accounts"][0]["allocation"] = {"stocks": 1.0}
    raw_config["goal"] = {"type": "retirement_income", "monthly_income_today": 4000}
    results = run_simulation(build_config(raw_config))

    block = scenario_withdrawals(results)

    assert block["n_years"] == 30
    assert [s["percentile"] for s in block["scenarios"]] == [10, 25, 50]
    for scenario in block["scenarios"]:
        assert scenario["start_balance"] > 0
        # Rows run optimistic -> conservative (90th .. 10th).
        assert [r["percentile"] for r in scenario["rows"]] == [90, 75, 50, 25, 10]
        for row in scenario["rows"]:
            np.testing.assert_allclose(row["monthly"] * 12.0, row["annual"], rtol=1e-9)
            np.testing.assert_allclose(
                row["rate"], row["annual"] / scenario["start_balance"], rtol=1e-9
            )


def test_scenario_withdrawals_none_for_target_goal(raw_config, deterministic_market):
    raw_config["market"] = deterministic_market
    raw_config["accounts"][0]["allocation"] = {"stocks": 1.0}
    raw_config["goal"] = {"type": "target_amount", "amount": 1_000_000}
    results = run_simulation(build_config(raw_config))

    assert scenario_withdrawals(results) is None
