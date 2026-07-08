"""Terminal summary and PNG chart output."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

from .config import GOAL_RETIREMENT_INCOME
from .results import SimulationResults

PERCENTILES = [10, 25, 50, 75, 90]

# Reference dataviz palette (light mode): sequential blue ramp for the
# percentile bands, status red reserved for failure mass, ink/chrome tokens
# for text and axes.
_BAND_OUTER = "#cde2fb"   # 10th-90th percentile band
_BAND_INNER = "#9ec5f4"   # 25th-75th percentile band
_MEDIAN = "#2a78d6"
_FAILURE = "#d03b3b"
_SURFACE = "#fcfcfb"
_INK = "#0b0b0b"
_INK_SECONDARY = "#52514e"
_INK_MUTED = "#898781"
_GRID = "#e1e0d9"
_BASELINE = "#c3c2b7"


def money(amount: float) -> str:
    return f"${amount:,.0f}"


def _compact_money(amount: float) -> str:
    def trim(value: float) -> str:
        return f"{value:,.1f}".rstrip("0").rstrip(".")

    if abs(amount) >= 1e9:
        return f"${trim(amount / 1e9)}B"
    if abs(amount) >= 1e6:
        return f"${trim(amount / 1e6)}M"
    if abs(amount) >= 1e3:
        return f"${trim(amount / 1e3)}K"
    return f"${amount:.0f}"


def format_summary(results: SimulationResults) -> str:
    config = results.config
    person = config.person
    goal = config.goal
    lines: list[str] = []
    add = lines.append

    add("=" * 66)
    add("Monte Carlo Retirement Simulation")
    add("=" * 66)
    if goal.type == GOAL_RETIREMENT_INCOME:
        add(f"Goal: {money(goal.monthly_income_today)}/month in today's dollars, "
            f"ages {person.retirement_age}-{person.death_age}")
    else:
        add(f"Goal: reach {money(goal.amount)} ({goal.basis} dollars) by age {person.retirement_age}")
    if config.active_social_security is not None:
        ss = config.active_social_security
        ss_line = f"Social Security: {money(ss.monthly_benefit_today)}/month (today's $) from age {ss.claiming_age}"
        if ss.pia_monthly is not None:
            ss_line += f" (from PIA {money(ss.pia_monthly)} at FRA {ss.full_retirement_age:g})"
        add(ss_line)
    starting = sum(a.balance for a in config.accounts)
    add(f"Starting balance: {money(starting)} across {len(config.accounts)} account(s)")
    seed_note = f", seed {results.seed}" if results.seed is not None else ""
    add(f"Simulations: {results.n_sims:,}{seed_note}")
    add("")

    probability = results.success_probability()
    label, _severity = results.score_band(probability)
    add(f"  SUCCESS PROBABILITY: {probability:.1%}  —  {label}")
    horizon_age = int(results.ages[-1])
    at_confidence = results.confidence_outcome(0.90, real=True)
    add(f"  At 90% confidence (significantly-below-average market): "
        f"{money(at_confidence)} in today's dollars at age {horizon_age}")
    add("")

    add(_percentile_table(results, results.retirement_index, f"Balance at retirement (age {person.retirement_age})"))
    if goal.type == GOAL_RETIREMENT_INCOME:
        add(_percentile_table(results, -1, f"Balance at death (age {person.death_age})"))
        failed = int(np.sum(~np.isnan(results.depletion_age)))
        if failed:
            add(f"Failed paths: {failed:,} of {results.n_sims:,} "
                f"(median depletion age {results.median_depletion_age():.0f})")
        else:
            add("Failed paths: none")
        add("")

    add(_assumptions_table(results))
    return "\n".join(lines)


def _percentile_table(results: SimulationResults, index: int, title: str) -> str:
    real = results.balances_at(index, real=True)
    nominal = results.balances_at(index, real=False)
    lines = [title, f"  {'percentile':<12}{'today’s $':>16}{'nominal $':>16}"]
    for p in PERCENTILES:
        lines.append(
            f"  {f'{p}th':<12}{money(np.percentile(real, p)):>16}{money(np.percentile(nominal, p)):>16}"
        )
    lines.append("")
    return "\n".join(lines)


def _assumptions_table(results: SimulationResults) -> str:
    market = results.config.market
    lines = ["Market assumptions (nominal, annual)", f"  {'series':<12}{'mean':>8}{'vol':>8}"]
    for name in market.asset_names:
        params = market.asset_classes[name]
        lines.append(f"  {name:<12}{params.mean:>8.1%}{params.vol:>8.1%}")
    lines.append(f"  {'inflation':<12}{market.inflation.mean:>8.1%}{market.inflation.vol:>8.1%}")
    fees = results.config.fees
    if fees.drag_bps or any(a.fee_drag_bps for a in results.config.accounts):
        lines.append(f"  {'fee drag':<12}{fees.drag_bps:>7.0f}bps (default; per-account may override)")
    return "\n".join(lines)


def save_charts(results: SimulationResults, output_dir: str | Path, show: bool = False) -> list[Path]:
    """Write the PNGs; with ``show`` also open interactive windows.

    The backend must be picked before any figure is created: headless Agg
    when only saving (works everywhere, e.g. CI), the platform's
    interactive backend when showing.
    """
    if not show and matplotlib.get_backend().lower() != "agg":
        plt.switch_backend("Agg")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    real = results.config.output.chart_dollars == "real"
    paths_and_figs = [
        _fan_chart(results, output_dir / "fan_chart.png", real),
        _scenario_chart(results, output_dir / "scenario_projections.png", real),
        _ending_balance_hist(results, output_dir / "ending_balance_hist.png", real),
    ]
    if show:
        plt.show()  # blocks until the windows are closed
    else:
        for _, fig in paths_and_figs:
            plt.close(fig)
    return [path for path, _ in paths_and_figs]


def _new_axes(title: str, subtitle: str):
    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
    fig.set_facecolor(_SURFACE)
    ax.set_facecolor(_SURFACE)
    fig.text(0.06, 0.955, title, fontsize=14, fontweight="bold", color=_INK)
    fig.text(0.06, 0.912, subtitle, fontsize=10, color=_INK_SECONDARY)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(_BASELINE)
    ax.grid(axis="y", color=_GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=_INK_MUTED, labelsize=9, length=0)
    return fig, ax


def _fan_chart(results: SimulationResults, path: Path, real: bool):
    ages = results.ages
    bands = results.percentile_bands(PERCENTILES, real=real)
    p10, p25, p50, p75, p90 = bands

    dollars = "today's dollars" if real else "nominal dollars"
    fig, ax = _new_axes("Portfolio balance by age", f"Median and percentile bands across "
                        f"{results.n_sims:,} simulated paths, {dollars}")

    ax.fill_between(ages, p10, p90, color=_BAND_OUTER, linewidth=0)
    ax.fill_between(ages, p25, p75, color=_BAND_INNER, linewidth=0)
    ax.plot(ages, p50, color=_MEDIAN, linewidth=2, solid_capstyle="round", solid_joinstyle="round")

    # Direct labels at the right edge instead of a legend.
    pad = (ages[-1] - ages[0]) * 0.012
    for value, label, color in [
        (p90[-1], "90th", _INK_MUTED),
        (p75[-1], "75th", _INK_MUTED),
        (p50[-1], "median", _INK_SECONDARY),
        (p25[-1], "25th", _INK_MUTED),
        (p10[-1], "10th", _INK_MUTED),
    ]:
        ax.annotate(label, (ages[-1] + pad, value), fontsize=8.5, color=color, va="center")

    # Stagger the marker labels so close events (e.g. retirement at 62,
    # Social Security at 67) don't collide.
    for i, (age, label) in enumerate(_event_markers(results)):
        ax.axvline(age, color=_BASELINE, linewidth=1)
        ax.annotate(label, (age, 1.0 - 0.045 * i), xycoords=("data", "axes fraction"),
                    xytext=(4, -2), textcoords="offset points",
                    fontsize=8.5, color=_INK_MUTED, va="top")

    ax.set_xlim(ages[0], ages[-1] + (ages[-1] - ages[0]) * 0.08)
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_formatter(lambda value, _pos: _compact_money(value))
    ax.set_xlabel("Age", fontsize=9, color=_INK_MUTED)

    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(path, facecolor=_SURFACE)
    return path, fig


# Ordered market scenarios, worst first: (percentile, label, blue ramp step).
# Lighter = worse market, same hue — these are ordered outcomes of one
# quantity, not independent series.
_SCENARIOS = [
    (10, "significantly below average market (10th pct)", "#86b6ef"),
    (25, "below average market (25th pct)", "#5598e7"),
    (50, "average market (50th pct)", "#2a78d6"),
]


def _scenario_chart(results: SimulationResults, path: Path, real: bool):
    ages = results.ages
    bands = results.percentile_bands([p for p, _, _ in _SCENARIOS], real=real)

    dollars = "today's dollars" if real else "nominal dollars"
    fig, ax = _new_axes("Market scenario projections",
                        f"Total balance if markets perform at the given percentile of "
                        f"{results.n_sims:,} simulated paths, {dollars}")

    pad = (ages[-1] - ages[0]) * 0.012
    for (percentile, label, color), values in zip(_SCENARIOS, bands):
        ax.plot(ages, values, color=color, linewidth=2, label=label,
                solid_capstyle="round", solid_joinstyle="round")
        ax.annotate(f"{percentile}th", (ages[-1] + pad, values[-1]),
                    fontsize=8.5, color=_INK_MUTED, va="center")

    for i, (age, label) in enumerate(_event_markers(results)):
        ax.axvline(age, color=_BASELINE, linewidth=1)
        ax.annotate(label, (age, 1.0 - 0.045 * i), xycoords=("data", "axes fraction"),
                    xytext=(4, -2), textcoords="offset points",
                    fontsize=8.5, color=_INK_MUTED, va="top")

    legend = ax.legend(loc="upper left", frameon=False, fontsize=8.5,
                       handlelength=1.6, reverse=True)
    for text in legend.get_texts():
        text.set_color(_INK_SECONDARY)

    ax.set_xlim(ages[0], ages[-1] + (ages[-1] - ages[0]) * 0.08)
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_formatter(lambda value, _pos: _compact_money(value))
    ax.set_xlabel("Age", fontsize=9, color=_INK_MUTED)

    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(path, facecolor=_SURFACE)
    return path, fig


def _event_markers(results: SimulationResults) -> list[tuple[int, str]]:
    person = results.config.person
    markers = []
    if results.ages[0] < person.retirement_age < results.ages[-1]:
        markers.append((person.retirement_age, "retirement"))
    ss = results.config.active_social_security
    if ss is not None and results.ages[0] < ss.claiming_age < results.ages[-1]:
        markers.append((ss.claiming_age, "social security"))
    return markers


def _ending_balance_hist(results: SimulationResults, path: Path, real: bool):
    goal = results.config.goal
    horizon_age = int(results.ages[-1])
    balances = results.balances_at(-1, real=real)

    dollars = "today's dollars" if real else "nominal dollars"
    at = "death" if goal.type == GOAL_RETIREMENT_INCOME else "retirement"
    fig, ax = _new_axes(f"Ending balance at {at} (age {horizon_age})",
                        f"Distribution across {results.n_sims:,} simulated paths, {dollars}")

    surviving = balances[balances > 0]
    n_failed = int(np.sum(balances <= 0))

    # A linear axis over the full range would be dominated by a handful of
    # extreme paths; clip at the 99th percentile and note the excluded tail.
    clip = float(np.percentile(surviving, 99)) if surviving.size else 1.0
    n_clipped = int(np.sum(surviving > clip))
    counts, edges, _ = ax.hist(
        np.minimum(surviving, clip), bins=48, range=(0, clip),
        color=_MEDIAN, edgecolor=_SURFACE, linewidth=0.8,
    )
    # Headroom so the corner annotations clear the tallest bar.
    ax.set_ylim(top=max(counts.max(), n_failed) * 1.15)

    if n_failed:
        width = edges[1] - edges[0]
        ax.bar([-width], [n_failed], width=width * 0.9, color=_FAILURE,
               edgecolor=_SURFACE, linewidth=0.8)
        ax.annotate(f"{n_failed:,} of {results.n_sims:,} paths depleted (red)",
                    (0.02, 0.96), xycoords="axes fraction",
                    fontsize=8.5, color=_INK_SECONDARY, va="top")
    if n_clipped:
        ax.annotate(f"top 1% of paths (> {_compact_money(clip)}) grouped in last bin",
                    (0.98, 0.96), xycoords="axes fraction",
                    fontsize=8.5, color=_INK_MUTED, ha="right", va="top")

    median = float(np.median(balances))
    ax.axvline(median, ymax=0.88, color=_BASELINE, linewidth=1)
    ax.annotate(f"median {_compact_money(median)}", (median, 0.88),
                xycoords=("data", "axes fraction"), xytext=(4, -2),
                textcoords="offset points", fontsize=8.5, color=_INK_MUTED, va="top")

    ax.xaxis.set_major_formatter(lambda value, _pos: _compact_money(value))
    ax.set_ylabel("Paths", fontsize=9, color=_INK_MUTED)

    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(path, facecolor=_SURFACE)
    return path, fig
