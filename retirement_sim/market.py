"""Correlated asset-return and inflation path generation.

All series are drawn jointly as a multivariate normal in log(1 + r) space
(i.e. lognormal growth factors), so returns can never fall below -100% and
inflation shocks are correlated with asset returns. The per-series log
parameters are moment-matched so the sampled arithmetic mean/vol equal the
configured values (see SeriesParams.log_params).
"""

from __future__ import annotations

import numpy as np

from .config import MarketConfig


def generate_paths(
    market: MarketConfig, n_sims: int, n_years: int, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """Draw annual return and inflation paths.

    Returns:
        asset_returns: shape (n_sims, n_years, n_assets), arithmetic returns.
        inflation: shape (n_sims, n_years), annual inflation rates.
    """
    mu, cov = market.log_mean_cov()
    # Eigendecomposition instead of Cholesky: the covariance is singular
    # whenever any vol is 0 (the deterministic test setup), which Cholesky
    # rejects.
    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    factor = eigenvectors * np.sqrt(np.clip(eigenvalues, 0.0, None))

    z = rng.standard_normal((n_sims, n_years, len(mu)))
    growth = np.exp(mu + z @ factor.T)
    return growth[..., :-1] - 1.0, growth[..., -1] - 1.0
