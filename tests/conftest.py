import copy

import pytest
from fastapi.testclient import TestClient

from retirement_sim.web import create_app

# Invite code the auth tests sign up with (see the auth_env fixture).
SIGNUP_CODE = "test-code"

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


@pytest.fixture
def auth_env(monkeypatch):
    """Enable signup with a known invite code and allow cookies over HTTP."""
    monkeypatch.setenv("SIGNUP_CODE", SIGNUP_CODE)
    monkeypatch.setenv("COOKIE_SECURE", "0")


@pytest.fixture
def client_factory(tmp_path, auth_env):
    """Factory for TestClients that all share one on-disk SQLite database.

    Two clients on the same DB stand in for two browsers hitting the same
    server — exactly what the per-user isolation tests need. Each client keeps
    its own cookie jar, so logging one in doesn't authenticate the other.
    """
    db_path = tmp_path / "app.db"

    def make() -> TestClient:
        return TestClient(create_app(db_path=db_path))

    return make


def signup(client, username="alice", password="password123", code=SIGNUP_CODE):
    """Sign up (and thereby log in) a user on ``client``; returns the response."""
    return client.post(
        "/api/auth/signup",
        json={"username": username, "password": password, "invite_code": code},
    )
