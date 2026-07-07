import dataclasses

import numpy as np
import pytest

from retirement_sim.config import ConfigError, MarketConfig, SeriesParams
from retirement_sim.market import _read_returns_csv, generate_paths

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


# --- bootstrap mode -------------------------------------------------------

MARKET_B = dataclasses.replace(MARKET, method="bootstrap", block_years=3)


def _write_csv(tmp_path, n_hist=10, header="year,stocks,bonds,inflation"):
    # Returns encode the historical row index (stocks = i/1000) so tests can
    # decode which year each sampled value came from; bonds = stocks + 0.01
    # proves rows are sampled jointly.
    lines = [header]
    for i in range(n_hist):
        lines.append(f"{1950 + i},{i / 1000},{i / 1000 + 0.01},{i / 100000}")
    path = tmp_path / "returns.csv"
    path.write_text("\n".join(lines) + "\n")
    return dataclasses.replace(MARKET_B, data_path=str(path))


def test_bootstrap_values_come_from_dataset(tmp_path):
    market = _write_csv(tmp_path)
    asset_returns, inflation = generate_paths(market, 200, 12, np.random.default_rng(3))
    assert np.isin(asset_returns[:, :, 0], np.arange(10) / 1000).all()
    assert np.isin(inflation, np.arange(10) / 100000).all()


def test_bootstrap_blocks_are_consecutive_circular_years(tmp_path):
    market = _write_csv(tmp_path)  # n_hist=10, block_years=3
    asset_returns, _ = generate_paths(market, 500, 12, np.random.default_rng(4))
    idx = np.rint(asset_returns[:, :, 0] * 1000).astype(int)
    for t in range(11):
        if t % 3 == 2:  # block boundary: next year starts a fresh block
            continue
        np.testing.assert_array_equal(idx[:, t + 1], (idx[:, t] + 1) % 10)


def test_bootstrap_rows_sampled_jointly(tmp_path):
    market = _write_csv(tmp_path)
    asset_returns, _ = generate_paths(market, 200, 12, np.random.default_rng(5))
    np.testing.assert_allclose(
        asset_returns[:, :, 1], asset_returns[:, :, 0] + 0.01, atol=1e-12
    )


def test_bootstrap_shapes_and_truncation(tmp_path):
    market = _write_csv(tmp_path)  # block_years=3 does not divide 7
    asset_returns, inflation = generate_paths(market, 40, 7, np.random.default_rng(6))
    assert asset_returns.shape == (40, 7, 2)
    assert inflation.shape == (40, 7)


def test_bootstrap_seed_reproducibility():
    a = generate_paths(MARKET_B, 50, 10, np.random.default_rng(7))
    b = generate_paths(MARKET_B, 50, 10, np.random.default_rng(7))
    np.testing.assert_array_equal(a[0], b[0])
    np.testing.assert_array_equal(a[1], b[1])


def test_bootstrap_unknown_asset_raises(tmp_path):
    market = _write_csv(tmp_path)
    market = dataclasses.replace(
        market, asset_classes={**market.asset_classes, "gold": SeriesParams(0.05, 0.2)}
    )
    with pytest.raises(ConfigError, match="'gold' not found in historical data"):
        generate_paths(market, 10, 5, np.random.default_rng(0))


def test_bootstrap_missing_file_raises(tmp_path):
    market = dataclasses.replace(MARKET_B, data_path=str(tmp_path / "nope.csv"))
    with pytest.raises(ConfigError, match="cannot read"):
        generate_paths(market, 10, 5, np.random.default_rng(0))


def test_bootstrap_nonconsecutive_years_raises(tmp_path):
    path = tmp_path / "gap.csv"
    path.write_text("year,stocks,bonds,inflation\n1950,0.1,0.1,0.02\n1952,0.1,0.1,0.02\n")
    market = dataclasses.replace(MARKET_B, data_path=str(path))
    with pytest.raises(ConfigError, match="consecutive"):
        generate_paths(market, 10, 5, np.random.default_rng(0))


def test_bootstrap_block_longer_than_history_raises(tmp_path):
    market = dataclasses.replace(_write_csv(tmp_path), block_years=11)  # n_hist=10
    with pytest.raises(ConfigError, match="block_years"):
        generate_paths(market, 10, 5, np.random.default_rng(0))


# --- bootstrap recenter ---------------------------------------------------

# Bootstrap over the bundled dataset (real vols) so recentering only shifts
# location; stocks/bonds/inflation all exist as columns in the packaged CSV.
MARKET_BUNDLED = dataclasses.replace(MARKET, method="bootstrap", block_years=1)


def test_bootstrap_recenter_matches_configured_log_mean():
    market = dataclasses.replace(MARKET_BUNDLED, recenter=True)
    asset_returns, inflation = generate_paths(market, 300_000, 1, np.random.default_rng(1))
    for i, name in enumerate(["stocks", "bonds"]):
        target = market.asset_classes[name].log_params()[0]
        log_growth = np.log1p(asset_returns[:, 0, i])
        assert abs(log_growth.mean() - target) < 0.005
    infl_target = market.inflation.log_params()[0]
    assert abs(np.log1p(inflation[:, 0]).mean() - infl_target) < 0.005


def test_bootstrap_recenter_preserves_vol_and_comovement():
    # Recentering is a pure per-series shift in log space, so with the same seed
    # (same sampled rows) the log vols and cross-asset correlation are identical
    # to the raw bootstrap to machine precision.
    a_raw, _ = generate_paths(MARKET_BUNDLED, 200_000, 1, np.random.default_rng(2))
    a_rc, _ = generate_paths(
        dataclasses.replace(MARKET_BUNDLED, recenter=True), 200_000, 1, np.random.default_rng(2)
    )
    for i in range(2):
        assert abs(np.log1p(a_raw[:, 0, i]).std() - np.log1p(a_rc[:, 0, i]).std()) < 1e-9
    corr_raw = np.corrcoef(np.log1p(a_raw[:, 0, 0]), np.log1p(a_raw[:, 0, 1]))[0, 1]
    corr_rc = np.corrcoef(np.log1p(a_rc[:, 0, 0]), np.log1p(a_rc[:, 0, 1]))[0, 1]
    assert abs(corr_raw - corr_rc) < 1e-9


def test_bootstrap_recenter_default_off_is_raw_history():
    a_off, i_off = generate_paths(MARKET_BUNDLED, 50, 10, np.random.default_rng(7))
    hist = _read_returns_csv(None)[1]
    assert np.isin(a_off[:, :, 0], hist[:, 0]).all()  # untouched historical values


def test_bootstrap_recenter_returns_never_below_minus_100_percent():
    market = dataclasses.replace(MARKET_BUNDLED, recenter=True)
    asset_returns, inflation = generate_paths(market, 5_000, 20, np.random.default_rng(3))
    assert (asset_returns > -1.0).all()
    assert (inflation > -1.0).all()


# --- all (ensemble) mode --------------------------------------------------


def test_all_mode_pools_paths_from_every_model():
    market = dataclasses.replace(MARKET, method="all")
    asset_returns, inflation = generate_paths(market, 100, 10, np.random.default_rng(9))
    assert asset_returns.shape == (300, 10, 2)  # n_sims per model, pooled
    assert inflation.shape == (300, 10)

    # The first n_sims paths are the parametric draws: the ensemble consumes
    # the RNG in model order, starting from the same state.
    parametric, _ = generate_paths(MARKET, 100, 10, np.random.default_rng(9))
    np.testing.assert_array_equal(asset_returns[:100], parametric)

    # The bootstrap third only contains historical values, i.e. each model
    # really contributes its own paths.
    hist_stocks = _read_returns_csv(None)[1][:, 0]
    assert np.isin(asset_returns[200:, :, 0], hist_stocks).all()


def test_all_mode_seed_reproducibility():
    market = dataclasses.replace(MARKET, method="all")
    a = generate_paths(market, 50, 10, np.random.default_rng(7))
    b = generate_paths(market, 50, 10, np.random.default_rng(7))
    np.testing.assert_array_equal(a[0], b[0])
    np.testing.assert_array_equal(a[1], b[1])


def test_bundled_csv_sanity():
    columns, values = _read_returns_csv(None)
    assert columns == ("stocks", "bonds", "cash", "inflation")
    assert values.shape[0] >= 97  # 1928 through at least 2024
    assert ((values > -1.0) & (values < 2.0)).all()
    # 1931 is row 3 (data starts 1928): worst year of the Depression.
    assert abs(values[3, 0] - (-0.4384)) < 1e-9
    # 2008: -36.55% stocks alongside +20% Treasuries (flight to quality).
    assert abs(values[80, 0] - (-0.3655)) < 1e-9
    assert values[80, 1] > 0.15
