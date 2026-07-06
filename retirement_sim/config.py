"""Configuration schema, YAML loading, and validation.

User configs are plain YAML. The optional ``market:`` block is deep-merged
on top of the packaged ``defaults.yaml`` so users only override what they
care about.
"""

from __future__ import annotations

import importlib.resources
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml

GOAL_RETIREMENT_INCOME = "retirement_income"
GOAL_TARGET_AMOUNT = "target_amount"

ACCOUNT_TYPES = {"401k", "403b", "roth_401k", "trad_ira", "roth_ira", "brokerage", "hsa", "cash", "other"}

# Allocations must sum to 1 within this tolerance.
_ALLOC_TOL = 1e-6


class ConfigError(Exception):
    """Raised when a config file is invalid, with an actionable message."""


@dataclass(frozen=True)
class PersonConfig:
    current_age: int
    retirement_age: int
    death_age: int


@dataclass(frozen=True)
class SeriesParams:
    """Arithmetic annual mean and volatility of a return/inflation series."""

    mean: float
    vol: float

    def log_params(self) -> tuple[float, float]:
        """Moment-matched parameters of log(1 + r).

        Chosen so that lognormal growth factors reproduce the configured
        arithmetic mean and volatility exactly.
        """
        gross = 1.0 + self.mean
        var_log = math.log(1.0 + self.vol**2 / gross**2)
        return math.log(gross) - var_log / 2.0, math.sqrt(var_log)


@dataclass(frozen=True)
class MarketConfig:
    asset_classes: dict[str, SeriesParams]
    inflation: SeriesParams
    correlations: dict[str, float]

    @property
    def asset_names(self) -> list[str]:
        return list(self.asset_classes)

    @property
    def series_names(self) -> list[str]:
        """Asset classes in config order, with inflation always last."""
        return self.asset_names + ["inflation"]

    def _series_params(self) -> list[SeriesParams]:
        return [*self.asset_classes.values(), self.inflation]

    def correlation_matrix(self) -> np.ndarray:
        names = self.series_names
        index = {name: i for i, name in enumerate(names)}
        corr = np.eye(len(names))
        for key, rho in self.correlations.items():
            i, j = _parse_correlation_key(key, index)
            corr[i, j] = corr[j, i] = rho
        return corr

    def log_mean_cov(self) -> tuple[np.ndarray, np.ndarray]:
        """Mean vector and covariance matrix in log(1 + r) space."""
        params = [p.log_params() for p in self._series_params()]
        mu = np.array([m for m, _ in params])
        sigma = np.array([s for _, s in params])
        cov = self.correlation_matrix() * np.outer(sigma, sigma)
        return mu, cov


@dataclass(frozen=True)
class GlidePathPoint:
    age: float
    allocation: dict[str, float]


@dataclass(frozen=True)
class Account:
    name: str
    type: str
    balance: float
    allocation: dict[str, float] | None = None
    glide_path: tuple[GlidePathPoint, ...] | None = None
    # Annual fee drag (expense ratio) in basis points; None means "use the
    # plan-wide default" (``fees.drag_bps``).
    fee_drag_bps: float | None = None


@dataclass(frozen=True)
class ContributionPhase:
    """One segment of a contribution stream.

    ``annual_amount`` is in today's dollars if ``index_to_inflation``;
    ``extra_annual_increase`` compounds from ``start_age`` on top of any
    inflation indexing.
    """

    start_age: int
    annual_amount: float
    index_to_inflation: bool = True
    extra_annual_increase: float = 0.0


@dataclass(frozen=True)
class ContributionStream:
    """Contributions to one account, normalized to consecutive phases.

    The first phase starts at the person's current age; each scheduled
    change (e.g. a CoastFI downshift) opens a new phase at its age.
    """

    account: str
    phases: tuple[ContributionPhase, ...]

    def phase_at(self, age: int) -> ContributionPhase:
        active = self.phases[0]
        for phase in self.phases:
            if phase.start_age <= age:
                active = phase
        return active


@dataclass(frozen=True)
class Goal:
    type: str
    monthly_income_today: float | None = None
    amount: float | None = None
    basis: str = "real"


@dataclass(frozen=True)
class SocialSecurity:
    monthly_benefit_today: float
    claiming_age: int


@dataclass(frozen=True)
class FeesConfig:
    """Plan-wide default annual fee drag (expense ratio) in basis points.

    Applied multiplicatively to each account's balance every year, so a
    50 bps drag multiplies growth by (1 - 0.0050). An account may override
    it with its own ``fee_drag_bps``.
    """

    drag_bps: float = 0.0

    def account_fee(self, account: Account) -> float:
        """Effective annual fee fraction for ``account`` (bps -> fraction)."""
        bps = account.fee_drag_bps if account.fee_drag_bps is not None else self.drag_bps
        return bps / 10_000.0


@dataclass(frozen=True)
class SimulationSettings:
    n_sims: int = 10_000
    seed: int | None = None


@dataclass(frozen=True)
class OutputSettings:
    dir: str = "output"
    charts: bool = True
    chart_dollars: str = "real"
    show: bool = False


@dataclass(frozen=True)
class PlanConfig:
    person: PersonConfig
    accounts: tuple[Account, ...]
    contributions: tuple[ContributionStream, ...]
    goal: Goal
    market: MarketConfig
    social_security: SocialSecurity | None = None
    fees: FeesConfig = field(default_factory=FeesConfig)
    simulation: SimulationSettings = field(default_factory=SimulationSettings)
    output: OutputSettings = field(default_factory=OutputSettings)


def load_config(path: str | Path) -> PlanConfig:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text())
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except yaml.YAMLError as exc:
        raise ConfigError(f"could not parse {path}: {exc}") from None
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a YAML mapping at the top level")
    return build_config(raw)


def build_config(raw: dict[str, Any]) -> PlanConfig:
    for section in ("person", "accounts", "goal"):
        if section not in raw:
            raise ConfigError(f"missing required section: {section}")

    person = _build_person(raw["person"])
    market = _build_market(_deep_merge(_default_market(), raw.get("market") or {}))
    accounts = tuple(_build_account(a, market.asset_names) for a in _require_list(raw["accounts"], "accounts"))
    _check_unique_names(accounts)
    contributions = tuple(
        _build_contribution(c, person, {a.name for a in accounts})
        for c in _require_list(raw.get("contributions") or [], "contributions")
    )
    goal = _build_goal(raw["goal"])
    social_security = _build_social_security(raw.get("social_security"), person)
    fees = _build_fees(raw.get("fees") or {})
    simulation = _build_simulation(raw.get("simulation") or {})
    output = _build_output(raw.get("output") or {})

    _validate_correlations(market)
    return PlanConfig(
        person=person,
        accounts=accounts,
        contributions=contributions,
        goal=goal,
        market=market,
        social_security=social_security,
        fees=fees,
        simulation=simulation,
        output=output,
    )


def _default_market() -> dict[str, Any]:
    text = importlib.resources.files("retirement_sim").joinpath("defaults.yaml").read_text()
    return yaml.safe_load(text)["market"]


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _require_list(value: Any, name: str) -> list:
    if not isinstance(value, list):
        raise ConfigError(f"{name} must be a list")
    return value


def _build_person(raw: dict) -> PersonConfig:
    try:
        person = PersonConfig(
            current_age=int(raw["current_age"]),
            retirement_age=int(raw["retirement_age"]),
            death_age=int(raw["death_age"]),
        )
    except KeyError as exc:
        raise ConfigError(f"person is missing required field {exc}") from None
    if not person.current_age <= person.retirement_age:
        raise ConfigError("person: current_age must be <= retirement_age")
    if not person.retirement_age < person.death_age:
        raise ConfigError("person: retirement_age must be < death_age")
    return person


def _build_series(raw: Any, name: str) -> SeriesParams:
    if not isinstance(raw, dict) or "mean" not in raw:
        raise ConfigError(f"market.{name} must be a mapping with at least a `mean`")
    params = SeriesParams(mean=float(raw["mean"]), vol=float(raw.get("vol", 0.0)))
    if params.vol < 0:
        raise ConfigError(f"market.{name}: vol must be >= 0")
    if params.mean <= -1:
        raise ConfigError(f"market.{name}: mean must be > -100%")
    return params


def _build_market(raw: dict) -> MarketConfig:
    asset_classes = {
        str(name): _build_series(series, f"asset_classes.{name}")
        for name, series in (raw.get("asset_classes") or {}).items()
    }
    if not asset_classes:
        raise ConfigError("market.asset_classes must define at least one asset class")
    if "inflation" in asset_classes:
        raise ConfigError("`inflation` is reserved; configure it under market.inflation")
    return MarketConfig(
        asset_classes=asset_classes,
        inflation=_build_series(raw.get("inflation"), "inflation"),
        correlations={str(k): float(v) for k, v in (raw.get("correlations") or {}).items()},
    )


def _parse_correlation_key(key: str, index: dict[str, int]) -> tuple[int, int]:
    """Split e.g. ``stocks_bonds`` into two known series names.

    Names may themselves contain underscores, so try every split point.
    """
    for pos in range(1, len(key)):
        if key[pos] != "_":
            continue
        left, right = key[:pos], key[pos + 1 :]
        if left in index and right in index:
            if left == right:
                raise ConfigError(f"market.correlations.{key}: a series cannot correlate with itself")
            return index[left], index[right]
    known = ", ".join(index)
    raise ConfigError(f"market.correlations.{key} does not name two known series (known: {known})")


def _validate_correlations(market: MarketConfig) -> None:
    for key, rho in market.correlations.items():
        if not -1.0 <= rho <= 1.0:
            raise ConfigError(f"market.correlations.{key}: correlation must be in [-1, 1]")
    corr = market.correlation_matrix()
    eigenvalues = np.linalg.eigvalsh(corr)
    if eigenvalues.min() < -1e-8:
        raise ConfigError(
            "market.correlations does not form a valid (positive semi-definite) "
            "correlation matrix; reduce the magnitude of one or more correlations"
        )


def _build_allocation(raw: Any, context: str, asset_names: list[str]) -> dict[str, float]:
    if not isinstance(raw, dict) or not raw:
        raise ConfigError(f"{context}: allocation must be a non-empty mapping of asset class -> weight")
    allocation = {}
    for name, weight in raw.items():
        if name not in asset_names:
            raise ConfigError(
                f"{context}: unknown asset class `{name}` (known: {', '.join(asset_names)})"
            )
        weight = float(weight)
        if weight < 0:
            raise ConfigError(f"{context}: allocation weights must be >= 0")
        allocation[str(name)] = weight
    total = sum(allocation.values())
    if abs(total - 1.0) > _ALLOC_TOL:
        raise ConfigError(f"{context}: allocation weights sum to {total:g}, expected 1.0")
    return allocation


def _build_account(raw: dict, asset_names: list[str]) -> Account:
    name = raw.get("name")
    if not name:
        raise ConfigError("every account needs a `name`")
    context = f"account {name}"
    acct_type = str(raw.get("type", "other"))
    if acct_type not in ACCOUNT_TYPES:
        raise ConfigError(f"{context}: unknown type `{acct_type}` (known: {', '.join(sorted(ACCOUNT_TYPES))})")
    balance = float(raw.get("balance", 0.0))
    if balance < 0:
        raise ConfigError(f"{context}: balance must be >= 0")

    fee_drag_bps = raw.get("fee_drag_bps")
    if fee_drag_bps is not None:
        fee_drag_bps = float(fee_drag_bps)
        if fee_drag_bps < 0:
            raise ConfigError(f"{context}: fee_drag_bps must be >= 0")

    has_alloc = "allocation" in raw
    has_glide = "glide_path" in raw
    if has_alloc == has_glide:
        raise ConfigError(f"{context}: specify exactly one of `allocation` or `glide_path`")

    allocation = None
    glide_path = None
    if has_alloc:
        allocation = _build_allocation(raw["allocation"], context, asset_names)
    else:
        points = []
        for i, point in enumerate(_require_list(raw["glide_path"], f"{context}.glide_path")):
            points.append(
                GlidePathPoint(
                    age=float(point["age"]),
                    allocation=_build_allocation(
                        point.get("allocation"), f"{context}.glide_path[{i}]", asset_names
                    ),
                )
            )
        if not points:
            raise ConfigError(f"{context}: glide_path must contain at least one point")
        ages = [p.age for p in points]
        if sorted(ages) != ages or len(set(ages)) != len(ages):
            raise ConfigError(f"{context}: glide_path ages must be strictly increasing")
        glide_path = tuple(points)

    return Account(
        name=str(name),
        type=acct_type,
        balance=balance,
        allocation=allocation,
        glide_path=glide_path,
        fee_drag_bps=fee_drag_bps,
    )


def _check_unique_names(accounts: tuple[Account, ...]) -> None:
    seen = set()
    for account in accounts:
        if account.name in seen:
            raise ConfigError(f"duplicate account name: {account.name}")
        seen.add(account.name)


def _build_phase(raw: dict, start_age: int, context: str) -> ContributionPhase:
    if "annual_amount" not in raw:
        raise ConfigError(f"{context}: missing `annual_amount`")
    amount = float(raw["annual_amount"])
    if amount < 0:
        raise ConfigError(f"{context}: annual_amount must be >= 0")
    return ContributionPhase(
        start_age=start_age,
        annual_amount=amount,
        index_to_inflation=bool(raw.get("index_to_inflation", True)),
        extra_annual_increase=float(raw.get("extra_annual_increase", 0.0)),
    )


def _build_contribution(raw: dict, person: PersonConfig, account_names: set[str]) -> ContributionStream:
    account = raw.get("account")
    if account not in account_names:
        raise ConfigError(
            f"contribution references unknown account `{account}` (known: {', '.join(sorted(account_names))})"
        )
    context = f"contribution to {account}"
    phases = [_build_phase(raw, person.current_age, context)]
    previous_age = person.current_age
    for i, change in enumerate(_require_list(raw.get("changes") or [], f"{context}.changes")):
        change_context = f"{context}.changes[{i}]"
        if "age" not in change:
            raise ConfigError(f"{change_context}: missing `age`")
        age = int(change["age"])
        if age <= previous_age:
            raise ConfigError(f"{change_context}: change ages must be strictly increasing and > current_age")
        if age >= person.retirement_age:
            raise ConfigError(f"{change_context}: change age {age} is at/after retirement; contributions already stop then")
        phases.append(_build_phase(change, age, change_context))
        previous_age = age
    return ContributionStream(account=str(account), phases=tuple(phases))


def _build_goal(raw: dict) -> Goal:
    goal_type = raw.get("type")
    if goal_type == GOAL_RETIREMENT_INCOME:
        income = raw.get("monthly_income_today")
        if income is None or float(income) <= 0:
            raise ConfigError("goal: retirement_income requires a positive `monthly_income_today`")
        return Goal(type=goal_type, monthly_income_today=float(income))
    if goal_type == GOAL_TARGET_AMOUNT:
        amount = raw.get("amount")
        if amount is None or float(amount) <= 0:
            raise ConfigError("goal: target_amount requires a positive `amount`")
        basis = str(raw.get("basis", "real"))
        if basis not in ("real", "nominal"):
            raise ConfigError("goal.basis must be `real` or `nominal`")
        return Goal(type=goal_type, amount=float(amount), basis=basis)
    raise ConfigError(f"goal.type must be `{GOAL_RETIREMENT_INCOME}` or `{GOAL_TARGET_AMOUNT}`")


def _build_social_security(raw: Any, person: PersonConfig) -> SocialSecurity | None:
    if raw is None:
        return None
    try:
        ss = SocialSecurity(
            monthly_benefit_today=float(raw["monthly_benefit_today"]),
            claiming_age=int(raw["claiming_age"]),
        )
    except KeyError as exc:
        raise ConfigError(f"social_security is missing required field {exc}") from None
    if ss.monthly_benefit_today < 0:
        raise ConfigError("social_security: monthly_benefit_today must be >= 0")
    if ss.claiming_age > person.death_age:
        raise ConfigError("social_security: claiming_age is after death_age")
    return ss


def _build_fees(raw: dict) -> FeesConfig:
    if not isinstance(raw, dict):
        raise ConfigError("fees must be a mapping (e.g. fees: {drag_bps: 50})")
    drag_bps = float(raw.get("drag_bps", 0.0))
    if drag_bps < 0:
        raise ConfigError("fees.drag_bps must be >= 0")
    return FeesConfig(drag_bps=drag_bps)


def _build_simulation(raw: dict) -> SimulationSettings:
    settings = SimulationSettings(
        n_sims=int(raw.get("n_sims", 10_000)),
        seed=None if raw.get("seed") is None else int(raw["seed"]),
    )
    if settings.n_sims < 1:
        raise ConfigError("simulation.n_sims must be >= 1")
    return settings


def _build_output(raw: dict) -> OutputSettings:
    settings = OutputSettings(
        dir=str(raw.get("dir", "output")),
        charts=bool(raw.get("charts", True)),
        chart_dollars=str(raw.get("chart_dollars", "real")),
        show=bool(raw.get("show", False)),
    )
    if settings.chart_dollars not in ("real", "nominal"):
        raise ConfigError("output.chart_dollars must be `real` or `nominal`")
    return settings
