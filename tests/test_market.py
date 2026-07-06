import dataclasses

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

MARKET_T = dataclasses.replace(MARKET, method="student_t", tail_df=6.0)


def _big_sample(market=MARKET):
    rng = np.random.default_rng(123)
    return generate_paths(market, n_sims=400_000, n_years=1, rng=rng)


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


# --- student_t mode -------------------------------------------------------


def test_student_t_log_moments_match_config():
    # Moment matching is exact in log space (the t innovations have unit
    # variance by construction), even though arithmetic moments are only
    # approximate in this mode.
    asset_returns, _ = _big_sample(MARKET_T)
    n = asset_returns.shape[0]
    for i, params in enumerate([MARKET_T.asset_classes["stocks"], MARKET_T.asset_classes["bonds"]]):
        m, s = params.log_params()
        log_growth = np.log1p(asset_returns[:, 0, i])
        assert abs(log_growth.mean() - m) < 4 * s / np.sqrt(n)
        assert abs(log_growth.std() - s) < 0.01 * s


def test_student_t_arithmetic_mean_close():
    # No exact arithmetic guarantee under fat tails; loose sanity bound only.
    asset_returns, inflation = _big_sample(MARKET_T)
    assert abs(asset_returns[:, 0, 0].mean() - 0.09) < 0.005
    assert abs(asset_returns[:, 0, 1].mean() - 0.04) < 0.005
    assert abs(inflation.mean() - 0.025) < 0.005


def test_student_t_has_fat_tails():
    # Excess kurtosis of a t(6) is 3 (vs 0 for the parametric normal); the
    # clip trims a little. Assert well above Gaussian, below nothing silly.
    asset_returns, _ = _big_sample(MARKET_T)
    log_growth = np.log1p(asset_returns[:, 0, 0])
    z = (log_growth - log_growth.mean()) / log_growth.std()
    excess_kurtosis = (z**4).mean() - 3.0
    assert excess_kurtosis > 1.5

    parametric_returns, _ = _big_sample(MARKET)
    log_growth_normal = np.log1p(parametric_returns[:, 0, 0])
    zn = (log_growth_normal - log_growth_normal.mean()) / log_growth_normal.std()
    assert (zn**4).mean() - 3.0 < 0.5


def test_student_t_correlations_match_config():
    # The shared chi-square mixer preserves linear correlation exactly, but
    # the sample estimator is noisier under heavy tails -> wider tolerance.
    asset_returns, inflation = _big_sample(MARKET_T)
    log_growth = np.log1p(
        np.concatenate([asset_returns[:, 0, :], inflation], axis=1)
    )
    corr = np.corrcoef(log_growth, rowvar=False)
    assert abs(corr[0, 1] - 0.15) < 0.02   # stocks-bonds
    assert abs(corr[1, 2] - (-0.3)) < 0.02  # bonds-inflation
    assert abs(corr[0, 2]) < 0.02           # unspecified pair -> 0


def test_student_t_returns_never_below_minus_100_percent():
    asset_returns, inflation = _big_sample(MARKET_T)
    assert (asset_returns > -1.0).all()
    assert (inflation > -1.0).all()


def test_student_t_seed_reproducibility():
    a = generate_paths(MARKET_T, 50, 10, np.random.default_rng(7))
    b = generate_paths(MARKET_T, 50, 10, np.random.default_rng(7))
    np.testing.assert_array_equal(a[0], b[0])
    np.testing.assert_array_equal(a[1], b[1])


def test_student_t_zero_volatility_is_deterministic():
    market = MarketConfig(
        asset_classes={"stocks": SeriesParams(mean=0.06, vol=0.0)},
        inflation=SeriesParams(mean=0.03, vol=0.0),
        correlations={},
        method="student_t",
    )
    asset_returns, inflation = generate_paths(market, 20, 5, np.random.default_rng(0))
    np.testing.assert_allclose(asset_returns, 0.06, rtol=1e-12)
    np.testing.assert_allclose(inflation, 0.03, rtol=1e-12)


def test_parametric_rng_stream_unchanged_by_new_modes():
    # The student_t branch draws from the RNG only after the normal draw, so
    # parametric output for a given seed is identical to the pre-feature code.
    normal_z = np.random.default_rng(11).standard_normal((50, 10, 3))
    a, _ = generate_paths(MARKET, 50, 10, np.random.default_rng(11))
    mu, cov = MARKET.log_mean_cov()
    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    factor = eigenvectors * np.sqrt(np.clip(eigenvalues, 0.0, None))
    expected = np.exp(mu + normal_z @ factor.T) - 1.0
    np.testing.assert_array_equal(a, expected[..., :-1])
