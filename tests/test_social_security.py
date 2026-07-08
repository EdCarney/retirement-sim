import pytest

from retirement_sim.config import ConfigError, _ss_benefit_factor, build_config


def test_benefit_factor_known_points():
    # SSA reference: FRA 67, claim at 62 -> 70% of PIA; at 70 -> 124%.
    assert _ss_benefit_factor(67, 67) == pytest.approx(1.0)
    assert _ss_benefit_factor(62, 67) == pytest.approx(0.70)
    assert _ss_benefit_factor(70, 67) == pytest.approx(1.24)
    # Delayed credits stop accruing at 70.
    assert _ss_benefit_factor(72, 67) == pytest.approx(1.24)


def test_pia_derives_benefit(raw_config):
    raw_config["social_security"] = {"pia_monthly": 2000, "claiming_age": 62}
    config = build_config(raw_config)
    ss = config.social_security
    assert ss.monthly_benefit_today == pytest.approx(2000 * 0.70)
    assert ss.pia_monthly == 2000
    assert ss.full_retirement_age == 67


def test_pia_respects_full_retirement_age(raw_config):
    # With FRA 66, claiming at 62 is 48 months early:
    # 36 * 5/9% + 12 * 5/12% = 20% + 5% = 25% reduction -> 75% of PIA.
    raw_config["social_security"] = {
        "pia_monthly": 2000,
        "claiming_age": 62,
        "full_retirement_age": 66,
    }
    config = build_config(raw_config)
    assert config.social_security.monthly_benefit_today == pytest.approx(2000 * 0.75)


def test_explicit_benefit_still_works(raw_config):
    raw_config["social_security"] = {"monthly_benefit_today": 2500, "claiming_age": 67}
    config = build_config(raw_config)
    assert config.social_security.monthly_benefit_today == 2500
    assert config.social_security.pia_monthly is None


def test_benefit_and_pia_conflict(raw_config):
    raw_config["social_security"] = {
        "monthly_benefit_today": 2500,
        "pia_monthly": 2000,
        "claiming_age": 67,
    }
    with pytest.raises(ConfigError, match="exactly one"):
        build_config(raw_config)


def test_pia_claiming_age_out_of_range(raw_config):
    raw_config["social_security"] = {"pia_monthly": 2000, "claiming_age": 60}
    with pytest.raises(ConfigError, match="between 62 and 70"):
        build_config(raw_config)


def test_enabled_defaults_true(raw_config):
    raw_config["social_security"] = {"monthly_benefit_today": 2500, "claiming_age": 67}
    config = build_config(raw_config)
    assert config.social_security.enabled is True
    # Active accessor returns the benefit when enabled.
    assert config.active_social_security is config.social_security


def test_disabled_retains_values_but_is_inactive(raw_config):
    raw_config["social_security"] = {
        "monthly_benefit_today": 2500,
        "claiming_age": 67,
        "enabled": False,
    }
    config = build_config(raw_config)
    # The values are still parsed and kept, so the UI can toggle them back on...
    assert config.social_security is not None
    assert config.social_security.monthly_benefit_today == 2500
    assert config.social_security.enabled is False
    # ...but the plan runs as if there were no Social Security.
    assert config.active_social_security is None
