"""Correlated asset-return and inflation path generation.

Parametric modes draw all series jointly in log(1 + r) space (i.e.
lognormal-style growth factors), so returns can never fall below -100% and
inflation shocks are correlated with asset returns. The per-series log
parameters are moment-matched to the configured arithmetic mean/vol (see
SeriesParams.log_params): with `parametric` (Gaussian) innovations the sampled
arithmetic mean/vol match the configured values exactly; with `student_t`
innovations the match is exact in log space and approximate in arithmetic
space (heavier tails push the sampled arithmetic moments slightly above the
configured values).

The `bootstrap` mode instead resamples multi-year blocks of actual historical
returns and inflation (whole years taken jointly across series), so fat tails,
cross correlations, and serial correlation / sequence risk come straight from
history; the configured mean/vol/correlations are ignored.

The `all` mode is a model ensemble: it draws n_sims paths from each of the
three concrete models and pools them, so results reflect all models equally
(and generate_paths returns 3 * n_sims paths).
"""

from __future__ import annotations

import csv
import dataclasses
import functools
import importlib.resources
import io
import math

import numpy as np

from .config import ConfigError, MarketConfig

# Standardized innovations are clipped at this many log-space standard
# deviations. A Student-t has no moment generating function, so exp() of an
# unclipped t draw has infinite mean/variance; clipping keeps the tails fat
# over the realistic range while guaranteeing finite arithmetic moments.
_T_CLIP = 8.0


def generate_paths(
    market: MarketConfig, n_sims: int, n_years: int, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """Draw annual return and inflation paths.

    Returns:
        asset_returns: shape (n_sims, n_years, n_assets), arithmetic returns.
        inflation: shape (n_sims, n_years), annual inflation rates.
    """
    paths = _method_paths(market, n_sims, n_years, rng)
    return paths[..., :-1], paths[..., -1]


def _method_paths(
    market: MarketConfig, n_sims: int, n_years: int, rng: np.random.Generator
) -> np.ndarray:
    if market.method == "all":
        # Ensemble: n_sims paths from every concrete model, pooled so each
        # model carries equal weight in the combined distribution. Callers
        # must size downstream arrays from the returned shape, not n_sims.
        return np.concatenate(
            [
                _method_paths(dataclasses.replace(market, method=m), n_sims, n_years, rng)
                for m in ("parametric", "student_t", "bootstrap")
            ]
        )
    if market.method == "bootstrap":
        return _bootstrap_paths(market, n_sims, n_years, rng)
    return _parametric_paths(market, n_sims, n_years, rng)


def _parametric_paths(
    market: MarketConfig, n_sims: int, n_years: int, rng: np.random.Generator
) -> np.ndarray:
    """Lognormal paths; `student_t` swaps the innovations, nothing else."""
    mu, cov = market.log_mean_cov()
    # Eigendecomposition instead of Cholesky: the covariance is singular
    # whenever any vol is 0 (the deterministic test setup), which Cholesky
    # rejects.
    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    factor = eigenvectors * np.sqrt(np.clip(eigenvalues, 0.0, None))

    # z is drawn before the method branch so `parametric` consumes the RNG
    # stream exactly as it always has (seeded runs stay reproducible).
    z = rng.standard_normal((n_sims, n_years, len(mu)))
    if market.method == "student_t":
        # One chi-square mixing draw shared across all series in a (sim, year)
        # cell turns the jointly-Gaussian z into a proper multivariate
        # Student-t: correlations are preserved exactly and assets crash
        # together (tail dependence). sqrt((nu-2)/nu) rescales to unit
        # variance so the log-space moment matching stays exact.
        nu = market.tail_df
        w = rng.chisquare(nu, size=(n_sims, n_years, 1))
        z = np.clip(z * np.sqrt(nu / w) * math.sqrt((nu - 2.0) / nu), -_T_CLIP, _T_CLIP)
    return np.exp(mu + z @ factor.T) - 1.0


def _bootstrap_paths(
    market: MarketConfig, n_sims: int, n_years: int, rng: np.random.Generator
) -> np.ndarray:
    """Circular block bootstrap over the historical returns dataset.

    Blocks of `market.block_years` consecutive historical years are sampled
    with uniformly random start positions, treating the dataset as a ring so
    every year is equally likely; whole rows are taken, preserving the
    historical co-movement of assets and inflation within each year.
    """
    data = _historical_returns(market)
    n_hist = data.shape[0]
    block = market.block_years
    if block > n_hist:
        raise ConfigError(
            f"market.bootstrap.block_years ({block}) exceeds the "
            f"{n_hist} years of historical data"
        )
    n_blocks = -(-n_years // block)  # ceil
    starts = rng.integers(0, n_hist, size=(n_sims, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)) % n_hist
    return data[idx.reshape(n_sims, -1)[:, :n_years]]


def _historical_returns(market: MarketConfig) -> np.ndarray:
    """Historical data as (n_years, n_series) in `market.series_names` order."""
    columns, values = _read_returns_csv(market.data_path)
    missing = [name for name in market.series_names if name not in columns]
    if missing:
        raise ConfigError(
            f"market.method bootstrap: asset class '{missing[0]}' not found in "
            f"historical data (columns: {', '.join(columns)})"
        )
    return values[:, [columns.index(name) for name in market.series_names]]


@functools.lru_cache(maxsize=8)
def _read_returns_csv(path: str | None) -> tuple[tuple[str, ...], np.ndarray]:
    """Parse a returns CSV into (column names, float array), skipping comments.

    The packaged 1928+ US dataset is used when `path` is None. Expected layout:
    a `year` column of consecutive years (blocks assume row t+1 is the year
    after row t), plus one decimal-returns column per series.
    """
    if path is None:
        text = (
            importlib.resources.files("retirement_sim")
            .joinpath("historical_returns.csv")
            .read_text()
        )
    else:
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError as exc:
            raise ConfigError(f"market.bootstrap.data: cannot read {path}: {exc}") from exc
    lines = [line for line in io.StringIO(text) if not line.startswith("#")]
    rows = list(csv.reader(lines))
    if not rows or rows[0][0] != "year":
        raise ConfigError("market.bootstrap.data: first column must be `year`")
    columns = tuple(rows[0][1:])
    try:
        years = [int(row[0]) for row in rows[1:]]
        values = np.array([[float(v) for v in row[1:]] for row in rows[1:]])
    except ValueError as exc:
        raise ConfigError(f"market.bootstrap.data: malformed row: {exc}") from exc
    if any(b - a != 1 for a, b in zip(years, years[1:])):
        raise ConfigError("market.bootstrap.data: `year` column must be consecutive years")
    return columns, values
