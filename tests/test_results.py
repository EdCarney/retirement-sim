import numpy as np

from retirement_sim.config import build_config
from retirement_sim.simulate import run_simulation


def _run(raw):
    return run_simulation(build_config(raw))


def test_score_band_thresholds(raw_config, deterministic_market):
    raw_config["market"] = deterministic_market
    results = _run(raw_config)

    assert results.score_band(0.95) == ("On track", "ok")
    assert results.score_band(0.90) == ("On track", "ok")
    assert results.score_band(0.85) == ("Good", "ok")
    assert results.score_band(0.70) == ("Fair", "warn")
    assert results.score_band(0.50) == ("Needs attention", "bad")
    assert results.score_band(0.0) == ("Needs attention", "bad")


def test_confidence_outcome_is_lower_percentile(raw_config, deterministic_market):
    # Zero volatility -> every path is identical, so the 10th-percentile
    # (90% confidence) outcome equals the single closed-form ending balance.
    raw_config["market"] = deterministic_market
    raw_config["accounts"][0]["allocation"] = {"stocks": 1.0}
    raw_config["contributions"] = []
    raw_config["goal"] = {"type": "target_amount", "amount": 1}

    results = _run(raw_config)

    expected = 500_000 * 1.06**25
    assert results.confidence_outcome(0.90, real=False) == np.percentile(
        results.balances_at(-1, real=False), 10
    )
    np.testing.assert_allclose(results.confidence_outcome(0.90, real=False), expected, rtol=1e-9)


def test_confidence_outcome_orders_with_level(raw_config):
    # With real volatility, a higher confidence level (deeper into the bad
    # tail) must give a lower-or-equal outcome than a lower level.
    results = _run(raw_config)
    strict = results.confidence_outcome(0.95, real=True)
    lenient = results.confidence_outcome(0.75, real=True)
    assert strict <= lenient
