"""Correlated asset-return and inflation path generation.

All series are drawn jointly in log(1 + r) space (i.e. lognormal-style growth
factors), so returns can never fall below -100% and inflation shocks are
correlated with asset returns. The per-series log parameters are moment-matched
to the configured arithmetic mean/vol (see SeriesParams.log_params): with
`parametric` (Gaussian) innovations the sampled arithmetic mean/vol match the
configured values exactly; with `student_t` innovations the match is exact in
log space and approximate in arithmetic space (heavier tails push the sampled
arithmetic moments slightly above the configured values).
"""

from __future__ import annotations

import math

import numpy as np

from .config import MarketConfig

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
    paths = _parametric_paths(market, n_sims, n_years, rng)
    return paths[..., :-1], paths[..., -1]


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
