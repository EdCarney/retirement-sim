from pathlib import Path

import pytest

from retirement_sim.config import ConfigError, build_config, load_config

CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"


def test_example_configs_load():
    income = load_config(CONFIG_DIR / "example_income_goal.yaml")
    assert income.goal.type == "retirement_income"
    assert income.social_security is not None
    assert len(income.accounts) == 3
    # The CoastFI change becomes a second phase starting at 50.
    stream = income.contributions[0]
    assert [p.start_age for p in stream.phases] == [35, 50]
    assert stream.phase_at(49).annual_amount == 23000
    assert stream.phase_at(50).annual_amount == 8000

    target = load_config(CONFIG_DIR / "example_target_amount.yaml")
    assert target.goal.type == "target_amount"
    assert target.goal.amount == 2_500_000


def test_defaults_are_merged(raw_config):
    raw_config["market"] = {"inflation": {"mean": 0.03}}
    config = build_config(raw_config)
    assert config.market.inflation.mean == 0.03
    assert config.market.inflation.vol == 0.015  # untouched default
    assert config.market.asset_classes["stocks"].mean == 0.095  # untouched default


def test_fees_default_and_effective_fee(raw_config):
    # No fees block -> zero drag by default.
    config = build_config(raw_config)
    assert config.fees.drag_bps == 0.0
    assert config.fees.account_fee(config.accounts[0]) == 0.0

    # Global default applies to accounts without an override.
    raw_config["fees"] = {"drag_bps": 50}
    config = build_config(raw_config)
    assert config.fees.account_fee(config.accounts[0]) == pytest.approx(0.005)

    # Per-account override wins over the global default.
    raw_config["accounts"][0]["fee_drag_bps"] = 20
    config = build_config(raw_config)
    assert config.fees.account_fee(config.accounts[0]) == pytest.approx(0.002)


def test_negative_fees_rejected(raw_config):
    raw_config["fees"] = {"drag_bps": -10}
    with pytest.raises(ConfigError, match="fees.drag_bps"):
        build_config(raw_config)


def test_negative_account_fee_rejected(raw_config):
    raw_config["accounts"][0]["fee_drag_bps"] = -5
    with pytest.raises(ConfigError, match="fee_drag_bps"):
        build_config(raw_config)


def test_allocation_must_sum_to_one(raw_config):
    raw_config["accounts"][0]["allocation"] = {"stocks": 0.6, "bonds": 0.3}
    with pytest.raises(ConfigError, match="sum"):
        build_config(raw_config)


def test_unknown_asset_class_rejected(raw_config):
    raw_config["accounts"][0]["allocation"] = {"crypto": 1.0}
    with pytest.raises(ConfigError, match="unknown asset class"):
        build_config(raw_config)


def test_allocation_and_glide_path_mutually_exclusive(raw_config):
    raw_config["accounts"][0]["glide_path"] = [
        {"age": 40, "allocation": {"stocks": 1.0}}
    ]
    with pytest.raises(ConfigError, match="exactly one"):
        build_config(raw_config)


def test_ages_must_be_ordered(raw_config):
    raw_config["person"]["retirement_age"] = 39
    with pytest.raises(ConfigError, match="current_age"):
        build_config(raw_config)
    raw_config["person"]["retirement_age"] = 91
    with pytest.raises(ConfigError, match="death_age"):
        build_config(raw_config)


def test_contribution_unknown_account(raw_config):
    raw_config["contributions"] = [{"account": "nope", "annual_amount": 1000}]
    with pytest.raises(ConfigError, match="unknown account"):
        build_config(raw_config)


def test_salary_mode_contribution(raw_config):
    raw_config["contributions"] = [
        {"account": "main", "salary": 120_000, "savings_rate": 0.15}
    ]
    config = build_config(raw_config)
    phase = config.contributions[0].phases[0]
    assert phase.annual_amount == pytest.approx(18_000)
    # Salary mode defaults to Fidelity's inflation + 1.5% real growth.
    assert phase.extra_annual_increase == pytest.approx(0.015)
    assert phase.index_to_inflation is True


def test_salary_mode_increase_override(raw_config):
    raw_config["contributions"] = [
        {"account": "main", "salary": 100_000, "savings_rate": 0.1, "extra_annual_increase": 0.0}
    ]
    config = build_config(raw_config)
    phase = config.contributions[0].phases[0]
    assert phase.annual_amount == pytest.approx(10_000)
    assert phase.extra_annual_increase == 0.0  # explicit override wins


def test_salary_and_amount_conflict(raw_config):
    raw_config["contributions"] = [
        {"account": "main", "annual_amount": 5000, "salary": 100_000, "savings_rate": 0.1}
    ]
    with pytest.raises(ConfigError, match="not both"):
        build_config(raw_config)


def test_salary_mode_requires_both_fields(raw_config):
    raw_config["contributions"] = [{"account": "main", "salary": 100_000}]
    with pytest.raises(ConfigError, match="both `salary` and `savings_rate`"):
        build_config(raw_config)


def test_contribution_change_after_retirement(raw_config):
    raw_config["contributions"] = [
        {
            "account": "main",
            "annual_amount": 1000,
            "changes": [{"age": 70, "annual_amount": 0}],
        }
    ]
    with pytest.raises(ConfigError, match="retirement"):
        build_config(raw_config)


def test_contribution_change_ages_must_increase(raw_config):
    raw_config["contributions"] = [
        {
            "account": "main",
            "annual_amount": 1000,
            "changes": [
                {"age": 55, "annual_amount": 500},
                {"age": 50, "annual_amount": 200},
            ],
        }
    ]
    with pytest.raises(ConfigError, match="increasing"):
        build_config(raw_config)


def test_goal_validation(raw_config):
    raw_config["goal"] = {"type": "retirement_income"}
    with pytest.raises(ConfigError, match="monthly_income_today"):
        build_config(raw_config)
    raw_config["goal"] = {"type": "target_amount", "amount": 100, "basis": "banana"}
    with pytest.raises(ConfigError, match="basis"):
        build_config(raw_config)
    raw_config["goal"] = {"type": "lottery"}
    with pytest.raises(ConfigError, match="goal.type"):
        build_config(raw_config)


def test_non_psd_correlations_rejected(raw_config):
    raw_config["market"] = {
        "correlations": {
            "stocks_bonds": 0.95,
            "stocks_cash": 0.95,
            "bonds_cash": -0.95,
        }
    }
    with pytest.raises(ConfigError, match="positive semi-definite"):
        build_config(raw_config)


def test_unknown_correlation_series_rejected(raw_config):
    raw_config["market"] = {"correlations": {"stocks_gold": 0.5}}
    with pytest.raises(ConfigError, match="known series"):
        build_config(raw_config)


def test_correlation_names_with_underscores(raw_config):
    raw_config["market"] = {
        "asset_classes": {"intl_stocks": {"mean": 0.08, "vol": 0.18}},
        "correlations": {"intl_stocks_bonds": 0.2},
    }
    config = build_config(raw_config)
    corr = config.market.correlation_matrix()
    names = config.market.series_names
    i, j = names.index("intl_stocks"), names.index("bonds")
    assert corr[i, j] == 0.2


def test_market_method_defaults_to_parametric(raw_config):
    config = build_config(raw_config)
    assert config.market.method == "parametric"
    assert config.market.tail_df == 6.0


def test_market_method_student_t_merges_with_defaults(raw_config):
    raw_config["market"] = {"method": "student_t"}
    config = build_config(raw_config)
    assert config.market.method == "student_t"
    assert config.market.tail_df == 6.0  # default df survives the deep-merge
    assert config.market.asset_classes["stocks"].mean == 0.095  # untouched default

    raw_config["market"] = {"method": "student_t", "student_t": {"df": 4}}
    assert build_config(raw_config).market.tail_df == 4.0


def test_unknown_market_method_rejected(raw_config):
    raw_config["market"] = {"method": "banana"}
    with pytest.raises(ConfigError, match="market.method"):
        build_config(raw_config)


def test_student_t_df_must_exceed_two(raw_config):
    raw_config["market"] = {"method": "student_t", "student_t": {"df": 2}}
    with pytest.raises(ConfigError, match="student_t.df"):
        build_config(raw_config)


def test_market_method_bootstrap(raw_config):
    raw_config["market"] = {"method": "bootstrap"}
    config = build_config(raw_config)
    assert config.market.method == "bootstrap"
    assert config.market.block_years == 5  # default from defaults.yaml
    assert config.market.data_path is None  # packaged dataset

    raw_config["market"] = {
        "method": "bootstrap",
        "bootstrap": {"block_years": 3, "data": "my_returns.csv"},
    }
    config = build_config(raw_config)
    assert config.market.block_years == 3
    assert config.market.data_path == "my_returns.csv"


def test_market_method_all(raw_config):
    raw_config["market"] = {"method": "all"}
    assert build_config(raw_config).market.method == "all"


def test_bootstrap_block_years_must_be_positive(raw_config):
    raw_config["market"] = {"method": "bootstrap", "bootstrap": {"block_years": 0}}
    with pytest.raises(ConfigError, match="block_years"):
        build_config(raw_config)
