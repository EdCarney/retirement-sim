"""Web UI: a stateless FastAPI server wrapping the simulation engine.

Serves the built React app from ``frontend/dist`` and exposes a small JSON
API for validating, serializing, and running plan configs. The server holds
**no** plan state: the browser owns the list of plans (localStorage) and the
user's disk owns the YAML files (upload / download). Every endpoint is a pure
function of its request body, so nothing user-specific is ever written to the
server's filesystem — a prerequisite for hosting this multi-tenant.

Downloaded YAML stays CLI-compatible: ``/api/serialize`` is the single
canonical writer, so a file saved from the UI runs unchanged via
``retirement-sim`` / ``load_config``.
"""

from __future__ import annotations

import argparse
import threading
import webbrowser
from pathlib import Path
from typing import Any

import numpy as np
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import (
    ACCOUNT_TYPES,
    GOAL_RETIREMENT_INCOME,
    GOAL_TARGET_AMOUNT,
    MARKET_METHODS,
    ConfigError,
    PlanConfig,
    _default_market,
    build_config,
)
from .report import PERCENTILES, money
from .results import SimulationResults
from .simulate import run_simulation
from .withdrawal import scenario_withdrawals


class SimulateRequest(BaseModel):
    config: dict[str, Any]
    n_sims: int | None = None
    seed: int | None = None


class MaxWithdrawalRequest(BaseModel):
    config: dict[str, Any]
    n_sims: int | None = None
    seed: int | None = None


def create_app(frontend_dist: Path | None = None) -> FastAPI:
    app = FastAPI(title="Retirement Monte Carlo Simulator", docs_url=None, redoc_url=None)

    def build_or_422(raw: Any) -> PlanConfig:
        if not isinstance(raw, dict):
            raise HTTPException(422, "config must be a mapping")
        try:
            return build_config(raw)
        except ConfigError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/serialize")
    def serialize(raw: dict[str, Any]) -> dict[str, Any]:
        """Canonical YAML for a plan, for download.

        This is the single serializer used everywhere a file is written, so a
        downloaded plan byte-matches what the CLI reads back. The config need
        not be valid (a work-in-progress is still serializable); callers that
        want validity should hit ``/api/validate`` first.
        """
        text = yaml.safe_dump(raw, sort_keys=False, allow_unicode=True)
        return {"yaml": text}

    @app.post("/api/validate")
    def validate(raw: dict[str, Any]) -> dict[str, Any]:
        try:
            build_or_422(raw)
        except HTTPException as exc:
            return {"valid": False, "error": exc.detail}
        return {"valid": True, "error": None}

    @app.get("/api/schema")
    def schema() -> dict[str, Any]:
        defaults = _default_market()
        return {
            "account_types": sorted(ACCOUNT_TYPES),
            "goal_types": [GOAL_RETIREMENT_INCOME, GOAL_TARGET_AMOUNT],
            "goal_bases": ["real", "nominal"],
            "chart_dollars": ["real", "nominal"],
            "asset_classes": list(defaults["asset_classes"]),
            "market_methods": list(MARKET_METHODS),
            "market_defaults": defaults,
        }

    @app.post("/api/simulate")
    def simulate(request: SimulateRequest) -> dict[str, Any]:
        config = build_or_422(request.config)
        results = run_simulation(config, n_sims=request.n_sims, seed=request.seed)
        return results_payload(results)

    @app.post("/api/max-withdrawal")
    def max_withdrawal(request: MaxWithdrawalRequest) -> dict[str, Any] | None:
        config = build_or_422(request.config)
        results = run_simulation(config, n_sims=request.n_sims, seed=request.seed)
        return scenario_withdrawals(results)

    if frontend_dist is not None and frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


def results_payload(results: SimulationResults) -> dict[str, Any]:
    """Everything the frontend needs to render the results view, as JSON.

    Real and nominal variants are both included so the dollar toggle
    doesn't require re-running the simulation.
    """
    config = results.config
    person = config.person
    goal = config.goal

    def bands(real: bool) -> dict[str, list[float]]:
        values = results.percentile_bands(PERCENTILES, real=real)
        return {f"p{p}": _round_list(row) for p, row in zip(PERCENTILES, values)}

    def table(index: int, title: str) -> dict[str, Any]:
        real = results.balances_at(index, real=True)
        nominal = results.balances_at(index, real=False)
        return {
            "title": title,
            "age": int(results.ages[index]),
            "rows": [
                {
                    "percentile": p,
                    "real": float(np.percentile(real, p)),
                    "nominal": float(np.percentile(nominal, p)),
                }
                for p in PERCENTILES
            ],
        }

    def histogram(real: bool) -> dict[str, Any]:
        balances = results.balances_at(-1, real=real)
        surviving = balances[balances > 0]
        n_failed = int(np.sum(balances <= 0))
        # Same treatment as report.py: a linear axis over the full range
        # would be dominated by a few extreme paths.
        clip = float(np.percentile(surviving, 99)) if surviving.size else 1.0
        counts, edges = np.histogram(
            np.minimum(surviving, clip), bins=48, range=(0.0, clip)
        )
        return {
            "bin_edges": _round_list(edges),
            "counts": counts.tolist(),
            "n_failed": n_failed,
            "n_clipped": int(np.sum(surviving > clip)),
            "clip": clip,
            "median": float(np.median(balances)),
        }

    if goal.type == GOAL_RETIREMENT_INCOME:
        goal_text = (
            f"{money(goal.monthly_income_today)}/month in today's dollars, "
            f"ages {person.retirement_age}–{person.death_age}"
        )
    else:
        goal_text = f"reach {money(goal.amount)} ({goal.basis} dollars) by age {person.retirement_age}"

    markers = [{"age": person.retirement_age, "label": "retirement"}]
    if config.active_social_security is not None:
        ss = config.active_social_security
        if results.ages[0] < ss.claiming_age < results.ages[-1]:
            markers.append({"age": ss.claiming_age, "label": "social security"})
    markers = [m for m in markers if results.ages[0] < m["age"] < results.ages[-1]]

    tables = [table(results.retirement_index, f"Balance at retirement (age {person.retirement_age})")]
    if goal.type == GOAL_RETIREMENT_INCOME:
        tables.append(table(-1, f"Balance at death (age {person.death_age})"))

    market = config.market
    assumptions = [
        {"series": name, "mean": params.mean, "vol": params.vol}
        for name, params in market.asset_classes.items()
    ]
    assumptions.append(
        {"series": "inflation", "mean": market.inflation.mean, "vol": market.inflation.vol}
    )

    median_depletion = results.median_depletion_age()
    probability = results.success_probability()
    score_label, score_severity = results.score_band(probability)
    horizon_age = int(results.ages[-1])
    return {
        "goal": {"type": goal.type, "text": goal_text},
        "n_sims": results.n_sims,
        "seed": results.seed,
        "success_probability": probability,
        "score": {"label": score_label, "severity": score_severity},
        "confidence": {
            "level": 0.90,
            "percentile": 10,
            "age": horizon_age,
            "real": results.confidence_outcome(0.90, real=True),
            "nominal": results.confidence_outcome(0.90, real=False),
        },
        "failed_paths": int(np.sum(~np.isnan(results.depletion_age))),
        "median_depletion_age": median_depletion,
        "starting_balance": float(sum(a.balance for a in config.accounts)),
        "ages": results.ages.tolist(),
        "percentiles": PERCENTILES,
        "bands": {"real": bands(True), "nominal": bands(False)},
        "markers": markers,
        "tables": tables,
        "histogram": {
            "at": "death" if goal.type == GOAL_RETIREMENT_INCOME else "retirement",
            "age": int(results.ages[-1]),
            "real": histogram(True),
            "nominal": histogram(False),
        },
        "assumptions": assumptions,
        "max_withdrawal": scenario_withdrawals(results),
    }


def _round_list(values: np.ndarray) -> list[float]:
    return [round(float(v), 2) for v in values]


def _default_frontend_dist() -> Path:
    return Path(__file__).resolve().parent.parent / "frontend" / "dist"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="retirement-sim-web", description="Local web UI for the retirement simulator."
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = parser.parse_args(argv)

    frontend_dist = _default_frontend_dist()
    if not frontend_dist.is_dir():
        print(
            "note: frontend build not found; only the JSON API will be served.\n"
            "      build it with: cd frontend && npm install && npm run build"
        )
        frontend_dist = None

    app = create_app(frontend_dist)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Serving on {url}")
    if not args.no_browser:
        threading.Timer(0.8, webbrowser.open, [url]).start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
