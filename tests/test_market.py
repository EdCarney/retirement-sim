import numpy as np

from retirement_sim.config import MarketConfig, SeriesParams
from retirement_sim.market import generate_paths

MARKET = MarketConfig(
    asset_classes={
        "stocks": SeriesParams(mean=0.09, vol=0.18),
        "bonds": SeriesParams(mean=0.04, vol=0.05),
    },
    inflation=SeriesParams(mean=0.025, vol=0.015),
    correlations={"stocks_bonds": 0.15, "bonds_inflation": -0.3},
)


def _big_sample():
    rng = np.random.default_rng(123)
    return generate_paths(MARKET, n_sims=400_000, n_years=1, rng=rng)


def test_moments_match_config():
    asset_returns, inflation = _big_sample()
    n = asset_returns.shape[0]
    for i, params in enumerate([MARKET.asset_classes["stocks"], MARKET.asset_classes["bonds"]]):
        series = asset_returns[:, 0, i]
        se_mean = params.vol / np.sqrt(n)
        assert abs(series.mean() - params.mean) < 4 * se_mean
        assert abs(series.std() - params.vol) < 0.01 * params.vol + 1e-4
    assert abs(inflation.mean() - 0.025) < 4 * 0.015 / np.sqrt(n)


def test_correlations_match_config():
    asset_returns, inflation = _big_sample()
    log_growth = np.log1p(
        np.concatenate([asset_returns[:, 0, :], inflation], axis=1)
    )
    corr = np.corrcoef(log_growth, rowvar=False)
    assert abs(corr[0, 1] - 0.15) < 0.01   # stocks-bonds
    assert abs(corr[1, 2] - (-0.3)) < 0.01  # bonds-inflation
    assert abs(corr[0, 2]) < 0.01           # unspecified pair -> 0


def test_returns_never_below_minus_100_percent():
    asset_returns, inflation = _big_sample()
    assert (asset_returns > -1.0).all()
    assert (inflation > -1.0).all()


def test_seed_reproducibility():
    a = generate_paths(MARKET, 50, 10, np.random.default_rng(7))
    b = generate_paths(MARKET, 50, 10, np.random.default_rng(7))
    np.testing.assert_array_equal(a[0], b[0])
    np.testing.assert_array_equal(a[1], b[1])


def test_zero_volatility_is_deterministic():
    market = MarketConfig(
        asset_classes={"stocks": SeriesParams(mean=0.06, vol=0.0)},
        inflation=SeriesParams(mean=0.03, vol=0.0),
        correlations={},
    )
    asset_returns, inflation = generate_paths(market, 20, 5, np.random.default_rng(0))
    np.testing.assert_allclose(asset_returns, 0.06, rtol=1e-12)
    np.testing.assert_allclose(inflation, 0.03, rtol=1e-12)
