import numpy as np
import pytest

from retirement_sim.config import ContributionPhase, ContributionStream, build_config
from retirement_sim.simulate import apply_withdrawal, contribution_amounts, run_simulation


def _run(raw):
    return run_simulation(build_config(raw))


def test_zero_volatility_matches_closed_form(raw_config, deterministic_market):
    raw_config["market"] = deterministic_market
    raw_config["accounts"][0]["allocation"] = {"stocks": 1.0}
    raw_config["contributions"] = [
        {"account": "main", "annual_amount": 10_000, "index_to_inflation": False}
    ]
    raw_config["goal"] = {"type": "target_amount", "amount": 1_000_000}

    results = _run(raw_config)

    n = 25  # ages 40..64 contribute; snapshot at 65
    r = 0.06
    expected = 500_000 * (1 + r) ** n + 10_000 * sum((1 + r) ** j for j in range(1, n + 1))
    np.testing.assert_allclose(results.history[:, -1], expected, rtol=1e-9)
    assert results.success_probability() in (0.0, 1.0)


def test_inflation_indexed_contributions(raw_config, deterministic_market):
    deterministic_market["asset_classes"]["stocks"]["mean"] = 0.0
    deterministic_market["inflation"]["mean"] = 0.03
    raw_config["market"] = deterministic_market
    raw_config["person"] = {"current_age": 40, "retirement_age": 45, "death_age": 90}
    raw_config["accounts"][0]["balance"] = 0
    raw_config["accounts"][0]["allocation"] = {"stocks": 1.0}
    raw_config["contributions"] = [
        {"account": "main", "annual_amount": 10_000, "index_to_inflation": True}
    ]
    raw_config["goal"] = {"type": "target_amount", "amount": 1}

    results = _run(raw_config)

    # Zero growth: final balance is just the sum of indexed contributions,
    # year k contributing 10,000 * 1.03^k.
    expected = sum(10_000 * 1.03**k for k in range(5))
    np.testing.assert_allclose(results.balances_at(-1, real=False), expected, rtol=1e-9)


def test_contribution_phases_and_extra_increase():
    stream = ContributionStream(
        account="main",
        phases=(
            ContributionPhase(40, 10_000, index_to_inflation=False, extra_annual_increase=0.02),
            ContributionPhase(50, 4_000, index_to_inflation=False),
        ),
    )
    ones = np.ones(3)
    np.testing.assert_allclose(contribution_amounts(stream, 40, ones), 10_000)
    np.testing.assert_allclose(contribution_amounts(stream, 45, ones), 10_000 * 1.02**5)
    # The CoastFI change resets the base and its increase clock.
    np.testing.assert_allclose(contribution_amounts(stream, 50, ones), 4_000)
    np.testing.assert_allclose(contribution_amounts(stream, 55, ones), 4_000)

    indexed = ContributionStream(
        account="main", phases=(ContributionPhase(40, 10_000, index_to_inflation=True),)
    )
    cum_inflation = np.array([1.0, 1.1, 1.21])
    np.testing.assert_allclose(
        contribution_amounts(indexed, 41, cum_inflation), 10_000 * cum_inflation
    )


def test_deterministic_depletion_age(raw_config, deterministic_market):
    deterministic_market["asset_classes"]["stocks"]["mean"] = 0.05
    raw_config["market"] = deterministic_market
    raw_config["person"] = {"current_age": 65, "retirement_age": 65, "death_age": 95}
    raw_config["accounts"][0]["allocation"] = {"stocks": 1.0}
    raw_config["goal"] = {"type": "retirement_income", "monthly_income_today": 4000}

    # Independent reference iteration of the same convention:
    # withdraw at start of year, then grow.
    balance, expected_depletion = 500_000.0, None
    for age in range(65, 95):
        if balance < 48_000 - 1e-9:
            expected_depletion = age
            break
        balance = (balance - 48_000) * 1.05

    results = _run(raw_config)
    assert expected_depletion is not None
    assert results.success_probability() == 0.0
    np.testing.assert_array_equal(results.depletion_age, expected_depletion)


def test_social_security_covering_spending_means_no_withdrawals(raw_config, deterministic_market):
    deterministic_market["asset_classes"]["stocks"]["mean"] = 0.05
    raw_config["market"] = deterministic_market
    raw_config["person"] = {"current_age": 65, "retirement_age": 65, "death_age": 95}
    raw_config["accounts"][0]["allocation"] = {"stocks": 1.0}
    raw_config["goal"] = {"type": "retirement_income", "monthly_income_today": 4000}
    raw_config["social_security"] = {"monthly_benefit_today": 5000, "claiming_age": 65}

    results = _run(raw_config)

    assert results.success_probability() == 1.0
    np.testing.assert_allclose(results.history[:, -1], 500_000 * 1.05**30, rtol=1e-9)


def test_target_amount_basis(raw_config, deterministic_market):
    deterministic_market["inflation"]["mean"] = 0.03
    raw_config["market"] = deterministic_market
    raw_config["person"] = {"current_age": 40, "retirement_age": 50, "death_age": 90}
    raw_config["accounts"][0]["balance"] = 100_000
    raw_config["accounts"][0]["allocation"] = {"stocks": 1.0}

    # Nominal outcome: 100k * 1.06^10 ~= 179k; real: /1.03^10 ~= 133k.
    raw_config["goal"] = {"type": "target_amount", "amount": 150_000, "basis": "nominal"}
    assert _run(raw_config).success_probability() == 1.0

    raw_config["goal"] = {"type": "target_amount", "amount": 150_000, "basis": "real"}
    assert _run(raw_config).success_probability() == 0.0


def test_retirement_snapshot_is_pre_withdrawal(raw_config, deterministic_market):
    deterministic_market["asset_classes"]["stocks"]["mean"] = 0.05
    raw_config["market"] = deterministic_market
    raw_config["person"] = {"current_age": 60, "retirement_age": 65, "death_age": 90}
    raw_config["accounts"][0]["allocation"] = {"stocks": 1.0}

    results = _run(raw_config)
    np.testing.assert_allclose(
        results.balances_at(results.retirement_index, real=False), 500_000 * 1.05**5, rtol=1e-9
    )


def test_fee_drag_reduces_growth(raw_config, deterministic_market):
    raw_config["market"] = deterministic_market
    raw_config["accounts"][0]["allocation"] = {"stocks": 1.0}
    raw_config["contributions"] = []
    raw_config["goal"] = {"type": "target_amount", "amount": 1}
    raw_config["fees"] = {"drag_bps": 50}  # 0.50% per year

    results = _run(raw_config)

    n = 25  # ages 40..64 grow; snapshot at 65
    # Each year: grow 6%, then keep (1 - 0.005) after fees.
    expected = 500_000 * ((1.06) * (1 - 0.005)) ** n
    np.testing.assert_allclose(results.balances_at(-1, real=False), expected, rtol=1e-9)


def test_per_account_fee_overrides_global(raw_config, deterministic_market):
    raw_config["market"] = deterministic_market
    raw_config["accounts"][0]["allocation"] = {"stocks": 1.0}
    raw_config["accounts"][0]["fee_drag_bps"] = 0  # override the global default away
    raw_config["contributions"] = []
    raw_config["goal"] = {"type": "target_amount", "amount": 1}
    raw_config["fees"] = {"drag_bps": 50}

    results = _run(raw_config)

    # The per-account 0 bps wins, so growth is the plain 6% closed form.
    expected = 500_000 * 1.06**25
    np.testing.assert_allclose(results.balances_at(-1, real=False), expected, rtol=1e-9)


def test_apply_withdrawal_proportional_and_shortfall():
    balances = np.array([[600.0, 400.0], [10.0, 10.0], [0.0, 0.0]])
    shortfall = apply_withdrawal(balances, np.array([100.0, 100.0, 100.0]))

    np.testing.assert_array_equal(shortfall, [False, True, True])
    np.testing.assert_allclose(balances[0], [540.0, 360.0])  # proportional 10%
    np.testing.assert_allclose(balances[1], [0.0, 0.0])
    np.testing.assert_allclose(balances[2], [0.0, 0.0])
