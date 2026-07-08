"""Web UI: a FastAPI server wrapping the simulation engine.

Serves the built React app from ``frontend/dist`` and exposes a small JSON API
for validating, serializing, and running plan configs, plus authentication and
per-user plan storage.

Accounts and their saved plans are persisted server-side in SQLite (see
``retirement_sim.db``); everything except the auth endpoints and the static
assets requires a valid session cookie. The simulation endpoints themselves stay
pure functions of their request body — the simulation engine never touches the
database — but the server is no longer stateless overall, and it must run as a
**single instance** (one SQLite writer; see ``db``).

Downloaded YAML stays CLI-compatible: ``/api/serialize`` is the single
canonical writer, so a file saved from the UI runs unchanged via
``retirement-sim`` / ``load_config``.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import sqlite3
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import uvicorn
import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth
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
from .db import Database, default_db_path
from .report import PERCENTILES, money
from .results import SimulationResults
from .simulate import run_simulation
from .withdrawal import scenario_withdrawals

# Cap simulation size at the HTTP boundary: n_sims sets numpy array
# dimensions, so an unbounded value from an untrusted caller is an OOM / cost
# event in a hosted deployment. The CLI is a trusted local caller and is not
# clamped.
MAX_N_SIMS = 150_000

# Per-user storage limits. The size cap mirrors the frontend's MAX_UPLOAD_BYTES
# so a plan that uploads also saves; the count cap bounds one account's rows.
MAX_PLANS_PER_USER = 200
MAX_CONFIG_BYTES = 1_000_000


class SimulateRequest(BaseModel):
    config: dict[str, Any]
    n_sims: int | None = None
    seed: int | None = None


class MaxWithdrawalRequest(BaseModel):
    config: dict[str, Any]
    n_sims: int | None = None
    seed: int | None = None


class SignupRequest(BaseModel):
    username: str
    password: str
    invite_code: str


class LoginRequest(BaseModel):
    username: str
    password: str


class PlanCreate(BaseModel):
    id: str
    name: str
    config: dict[str, Any]


class PlanUpdate(BaseModel):
    name: str
    config: dict[str, Any]


def create_app(
    frontend_dist: Path | None = None, db_path: Path | None = None
) -> FastAPI:
    app = FastAPI(title="Retirement Monte Carlo Simulator", docs_url=None, redoc_url=None)
    database = Database(db_path or default_db_path())
    app.state.db = database

    def build_or_422(raw: Any) -> PlanConfig:
        if not isinstance(raw, dict):
            raise HTTPException(422, "config must be a mapping")
        try:
            return build_config(raw)
        except ConfigError as exc:
            raise HTTPException(422, str(exc)) from None

    def require_user(request: Request) -> sqlite3.Row:
        """Dependency: resolve the caller's session cookie to a user, or 401.

        Guards every non-auth ``/api`` endpoint. A missing, unknown, or expired
        session all surface as 401 so the SPA can send the caller to log in.
        """
        token = request.cookies.get(auth.SESSION_COOKIE)
        if not token:
            raise HTTPException(401, "not authenticated")
        user = database.get_session_user(auth.token_hash(token))
        if user is None:
            raise HTTPException(401, "session expired")
        return user

    def start_session(response: Response, user_id: int) -> None:
        token = auth.new_session_token()
        database.create_session(user_id, auth.token_hash(token), auth.session_expiry())
        response.set_cookie(
            auth.SESSION_COOKIE,
            token,
            max_age=int(auth.SESSION_TTL.total_seconds()),
            httponly=True,
            samesite="lax",
            secure=auth.cookie_secure(),
            path="/",
        )

    # ── auth ─────────────────────────────────────────────────────────────────

    @app.get("/api/auth/config")
    def auth_config() -> dict[str, Any]:
        """Public: lets the login screen show/hide the signup tab."""
        return {"signup_enabled": auth.signup_enabled()}

    @app.post("/api/auth/signup")
    def signup(req: SignupRequest, response: Response) -> dict[str, Any]:
        if not auth.signup_enabled():
            raise HTTPException(403, "signup is disabled")
        if not auth.check_signup_code(req.invite_code):
            raise HTTPException(403, "invalid invite code")
        username = req.username.strip()
        _validate_credentials(username, req.password)
        try:
            user = database.create_user(username, auth.hash_password(req.password))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "username already taken") from None
        start_session(response, user["id"])
        return {"user": _user_public(user)}

    @app.post("/api/auth/login")
    def login(req: LoginRequest, response: Response) -> dict[str, Any]:
        user = database.get_user_by_username(req.username.strip())
        # One generic error for both unknown user and wrong password so the
        # endpoint doesn't reveal which usernames exist.
        if user is None or not auth.verify_password(req.password, user["password_hash"]):
            raise HTTPException(401, "invalid username or password")
        database.delete_expired_sessions()
        start_session(response, user["id"])
        return {"user": _user_public(user)}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response) -> dict[str, Any]:
        token = request.cookies.get(auth.SESSION_COOKIE)
        if token:
            database.delete_session(auth.token_hash(token))
        response.delete_cookie(auth.SESSION_COOKIE, path="/")
        return {"ok": True}

    @app.get("/api/auth/me")
    def me(user: sqlite3.Row = Depends(require_user)) -> dict[str, Any]:
        return {"user": _user_public(user)}

    # ── plan CRUD (per user) ─────────────────────────────────────────────────

    @app.get("/api/plans")
    def list_plans(user: sqlite3.Row = Depends(require_user)) -> list[dict[str, Any]]:
        return [_plan_public(row) for row in database.list_plans(user["id"])]

    @app.post("/api/plans", status_code=201)
    def create_plan(
        req: PlanCreate, user: sqlite3.Row = Depends(require_user)
    ) -> dict[str, Any]:
        if database.count_plans(user["id"]) >= MAX_PLANS_PER_USER:
            raise HTTPException(409, f"plan limit reached ({MAX_PLANS_PER_USER})")
        config_json = _config_json_or_413(req.config)
        try:
            database.create_plan(user["id"], req.id, req.name, config_json)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "a plan with that id already exists") from None
        return {"id": req.id, "name": req.name, "config": req.config}

    @app.put("/api/plans/{plan_id}")
    def update_plan(
        plan_id: str, req: PlanUpdate, user: sqlite3.Row = Depends(require_user)
    ) -> dict[str, Any]:
        config_json = _config_json_or_413(req.config)
        if not database.update_plan(user["id"], plan_id, req.name, config_json):
            raise HTTPException(404, "no such plan")
        return {"id": plan_id, "name": req.name, "config": req.config}

    @app.delete("/api/plans/{plan_id}", status_code=204)
    def delete_plan(
        plan_id: str, user: sqlite3.Row = Depends(require_user)
    ) -> Response:
        if not database.delete_plan(user["id"], plan_id):
            raise HTTPException(404, "no such plan")
        return Response(status_code=204)

    # ── simulation / schema (auth-gated, but pure functions of the body) ─────

    @app.post("/api/serialize")
    def serialize(
        raw: dict[str, Any], _user: sqlite3.Row = Depends(require_user)
    ) -> dict[str, Any]:
        """Canonical YAML for a plan, for download.

        This is the single serializer used everywhere a file is written, so a
        downloaded plan byte-matches what the CLI reads back. The config need
        not be valid (a work-in-progress is still serializable); callers that
        want validity should hit ``/api/validate`` first.
        """
        text = yaml.safe_dump(raw, sort_keys=False, allow_unicode=True)
        return {"yaml": text}

    @app.post("/api/validate")
    def validate(
        raw: dict[str, Any], _user: sqlite3.Row = Depends(require_user)
    ) -> dict[str, Any]:
        try:
            build_or_422(raw)
        except HTTPException as exc:
            return {"valid": False, "error": exc.detail}
        return {"valid": True, "error": None}

    @app.get("/api/schema")
    def schema(_user: sqlite3.Row = Depends(require_user)) -> dict[str, Any]:
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
    def simulate(
        request: SimulateRequest, _user: sqlite3.Row = Depends(require_user)
    ) -> StreamingResponse:
        """Run a simulation, streaming progress then the final result.

        The response is newline-delimited JSON (NDJSON): zero or more
        ``{"type": "progress", "value": <0..1>}`` lines followed by one
        ``{"type": "result", "payload": ...}`` (or ``{"type": "error", ...}``)
        line. Config validation still happens up front, so an invalid config
        returns a plain ``422`` before the stream opens.
        """
        config = build_or_422(request.config)
        n_sims = _clamp_n_sims(request.n_sims, config)
        return StreamingResponse(
            _simulate_stream(config, n_sims, request.seed),
            media_type="application/x-ndjson",
            # Discourage proxy buffering so progress reaches the browser live.
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )

    @app.post("/api/max-withdrawal")
    def max_withdrawal(
        request: MaxWithdrawalRequest, _user: sqlite3.Row = Depends(require_user)
    ) -> dict[str, Any] | None:
        config = build_or_422(request.config)
        n_sims = _clamp_n_sims(request.n_sims, config)
        results = run_simulation(config, n_sims=n_sims, seed=request.seed)
        return scenario_withdrawals(results)

    if frontend_dist is not None and frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


def _user_public(row: sqlite3.Row) -> dict[str, Any]:
    """The safe, client-facing view of a user row (never the password hash)."""
    return {"id": row["id"], "username": row["username"]}


def _plan_public(row: sqlite3.Row) -> dict[str, Any]:
    """A stored plan row as the ``{id, name, config}`` shape the frontend uses."""
    return {"id": row["id"], "name": row["name"], "config": json.loads(row["config"])}


def _validate_credentials(username: str, password: str) -> None:
    if not (auth.MIN_USERNAME_LEN <= len(username) <= auth.MAX_USERNAME_LEN):
        raise HTTPException(
            400,
            f"username must be {auth.MIN_USERNAME_LEN}–{auth.MAX_USERNAME_LEN} characters",
        )
    if not (auth.MIN_PASSWORD_LEN <= len(password) <= auth.MAX_PASSWORD_LEN):
        raise HTTPException(
            400, f"password must be at least {auth.MIN_PASSWORD_LEN} characters"
        )


def _config_json_or_413(config: dict[str, Any]) -> str:
    """Serialize a plan config to JSON, rejecting oversized payloads with 413."""
    text = json.dumps(config)
    if len(text.encode("utf-8")) > MAX_CONFIG_BYTES:
        raise HTTPException(413, "config too large")
    return text


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


def _simulate_stream(
    config: PlanConfig, n_sims: int, seed: int | None
) -> Iterator[bytes]:
    """Yield NDJSON progress lines, then the final result (or error) line.

    The simulation runs on a worker thread that pushes events onto a queue;
    this generator drains them to the wire. numpy releases the GIL during the
    heavy array math, so the worker keeps computing while we block on the
    queue — progress genuinely reflects work in flight.
    """
    events: queue.Queue[tuple[str, Any]] = queue.Queue()

    def on_progress(fraction: float) -> None:
        events.put(("progress", fraction))

    def worker() -> None:
        try:
            results = run_simulation(
                config, n_sims=n_sims, seed=seed, on_progress=on_progress
            )
            events.put(("result", results_payload(results)))
        except Exception as exc:  # any failure is surfaced as an error line
            events.put(("error", str(exc)))

    threading.Thread(target=worker, daemon=True).start()

    # An immediate 0% makes the bar appear before path generation (the first,
    # un-instrumented chunk of work) completes.
    yield _ndjson({"type": "progress", "value": 0.0})
    while True:
        kind, value = events.get()
        if kind == "progress":
            yield _ndjson({"type": "progress", "value": value})
        elif kind == "result":
            yield _ndjson({"type": "result", "payload": value})
            return
        else:
            yield _ndjson({"type": "error", "error": value})
            return


def _ndjson(obj: dict[str, Any]) -> bytes:
    return (json.dumps(obj) + "\n").encode()


def _clamp_n_sims(override: int | None, config: PlanConfig) -> int:
    """Effective n_sims for a request, capped at ``MAX_N_SIMS``.

    Mirrors ``run_simulation``'s fallback (override, else the config's value)
    so the cap applies no matter which path a caller uses to inflate it.
    """
    n_sims = override if override is not None else config.simulation.n_sims
    return max(1, min(n_sims, MAX_N_SIMS))


def _round_list(values: np.ndarray) -> list[float]:
    return [round(float(v), 2) for v in values]


def _default_frontend_dist() -> Path:
    return Path(__file__).resolve().parent.parent / "frontend" / "dist"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="retirement-sim-web", description="Web server for the retirement simulator."
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="interface to bind (default: all)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="port to bind (default: $PORT, else 8000)",
    )
    args = parser.parse_args(argv)

    # App Service (and most container platforms) inject the port via $PORT.
    port = args.port if args.port is not None else int(os.environ.get("PORT", "8000"))

    frontend_dist = _default_frontend_dist()
    if not frontend_dist.is_dir():
        print(
            "note: frontend build not found; only the JSON API will be served.\n"
            "      build it with: cd frontend && npm install && npm run build"
        )
        frontend_dist = None

    app = create_app(frontend_dist)
    print(f"Serving on http://{args.host}:{port}")
    # log_level="warning" keeps request bodies (which carry plan data) out of
    # the logs — see the privacy note in the module docstring.
    uvicorn.run(app, host=args.host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
