from pathlib import Path

import numpy as np
import pytest

from retirement_sim.cli import main
from retirement_sim.config import build_config, load_config
from retirement_sim.simulate import run_simulation

CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"


@pytest.mark.parametrize(
    "config_name", ["example_income_goal.yaml", "example_target_amount.yaml"]
)
def test_cli_end_to_end(config_name, tmp_path, capsys):
    exit_code = main(
        [str(CONFIG_DIR / config_name), "--sims", "300", "--seed", "1", "--output-dir", str(tmp_path)]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "SUCCESS PROBABILITY" in out
    for name in ("fan_chart.png", "scenario_projections.png", "ending_balance_hist.png"):
        chart = tmp_path / name
        assert chart.exists() and chart.stat().st_size > 0


def test_income_example_results_are_sane():
    config = load_config(CONFIG_DIR / "example_income_goal.yaml")
    results = run_simulation(config, n_sims=1000, seed=2)

    probability = results.success_probability()
    assert 0.0 < probability < 1.0

    bands = results.percentile_bands([10, 50, 90])
    assert (bands[0] <= bands[1]).all() and (bands[1] <= bands[2]).all()
    # Real and nominal histories agree at t=0 and diverge after.
    np.testing.assert_allclose(results.real_history()[:, 0], results.history[:, 0])


def test_four_percent_rule_benchmark(raw_config):
    """Smell test vs the literature: a 60/40 portfolio spending an initial 4%
    over a 30-year retirement should succeed roughly 80-100% of the time."""
    raw_config["person"] = {"current_age": 65, "retirement_age": 65, "death_age": 95}
    raw_config["accounts"][0]["balance"] = 1_000_000
    raw_config["goal"] = {"type": "retirement_income", "monthly_income_today": 40_000 / 12}
    raw_config["simulation"] = {"n_sims": 4000, "seed": 3}

    probability = run_simulation(build_config(raw_config)).success_probability()
    assert 0.75 < probability <= 1.0
