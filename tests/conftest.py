import copy

import pytest

# Minimal valid raw config; tests mutate copies of this.
BASE_RAW = {
    "person": {"current_age": 40, "retirement_age": 65, "death_age": 90},
    "accounts": [
        {
            "name": "main",
            "type": "401k",
            "balance": 500_000,
            "allocation": {"stocks": 0.6, "bonds": 0.4},
        },
    ],
    "contributions": [],
    "goal": {"type": "retirement_income", "monthly_income_today": 4000},
    "simulation": {"n_sims": 100, "seed": 7},
}

# Market override that makes every series deterministic (all vols zero,
# zero inflation) with 100%-stocks accounts earning exactly 6%/yr.
DETERMINISTIC_MARKET = {
    "asset_classes": {
        "stocks": {"mean": 0.06, "vol": 0.0},
        "bonds": {"mean": 0.03, "vol": 0.0},
        "cash": {"mean": 0.02, "vol": 0.0},
    },
    "inflation": {"mean": 0.0, "vol": 0.0},
}


@pytest.fixture
def raw_config():
    return copy.deepcopy(BASE_RAW)


@pytest.fixture
def deterministic_market():
    return copy.deepcopy(DETERMINISTIC_MARKET)
