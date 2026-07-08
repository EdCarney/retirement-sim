"""API tests for the stateless web server (retirement_sim.web)."""

import copy
import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from retirement_sim.config import build_config
from retirement_sim.web import MAX_N_SIMS, _clamp_n_sims, create_app

CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"


def run_simulate(client, **payload):
    """POST /api/simulate and parse its NDJSON stream.

    Returns ``(result, progress)``: the final result payload and the list of
    progress fractions streamed before it.
    """
    response = client.post("/api/simulate", json=payload)
    assert response.status_code == 200
    result = None
    progress = []
    for line in response.text.splitlines():
        if not line.strip():
            continue
        msg = json.loads(line)
        if msg["type"] == "progress":
            progress.append(msg["value"])
        elif msg["type"] == "result":
            result = msg["payload"]
        elif msg["type"] == "error":
            raise AssertionError(f"simulation errored: {msg['error']}")
    return result, progress


@pytest.fixture
def example_income() -> dict:
    return yaml.safe_load((CONFIG_DIR / "example_income_goal.yaml").read_text())


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Endpoints are now auth-gated, so the shared client signs up (and stays
    # logged in via its cookie jar) before exercising the simulation API.
    monkeypatch.setenv("SIGNUP_CODE", "test-code")
    monkeypatch.setenv("COOKIE_SECURE", "0")
    c = TestClient(create_app(db_path=tmp_path / "app.db"))
    resp = c.post(
        "/api/auth/signup",
        json={"username": "tester", "password": "password123", "invite_code": "test-code"},
    )
    assert resp.status_code == 200
    return c


def test_requires_auth(tmp_path):
    # Without a session cookie, the simulation API is closed.
    anon = TestClient(create_app(db_path=tmp_path / "app.db"))
    assert anon.get("/api/schema").status_code == 401
    assert anon.post("/api/validate", json={"person": {}}).status_code == 401
    assert anon.post("/api/simulate", json={"config": {}}).status_code == 401


def test_no_filesystem_crud_endpoints(client):
    # The server owns no plan state; the storage endpoints are gone.
    assert client.get("/api/configs").status_code == 404
    assert client.get("/api/configs/example_income_goal.yaml").status_code == 404
    assert client.put("/api/configs/x.yaml", json={}).status_code == 404
    assert client.post("/api/configs/x.yaml").status_code == 404
    assert client.delete("/api/configs/x.yaml").status_code == 404


def test_serialize_roundtrips_to_cli_compatible_yaml(client, example_income, tmp_path):
    example_income["person"]["retirement_age"] = 60

    text = client.post("/api/serialize", json=example_income).json()["yaml"]

    # The canonical serializer preserves key order and stays CLI-loadable:
    # a downloaded file must run unchanged through load_config.
    assert text.startswith("person:")
    path = tmp_path / "downloaded.yaml"
    path.write_text(text)
    reloaded = build_config(yaml.safe_load(path.read_text()))
    assert reloaded.person.retirement_age == 60


def test_serialize_allows_incomplete_config(client):
    # A work-in-progress need not validate to be serialized for download.
    text = client.post("/api/serialize", json={"person": {}}).json()["yaml"]
    assert yaml.safe_load(text) == {"person": {}}


def test_validate_endpoint(client, example_income):
    assert client.post("/api/validate", json=example_income).json() == {
        "valid": True,
        "error": None,
    }

    bad = copy.deepcopy(example_income)
    bad["accounts"][0]["allocation"] = {"stocks": 0.5}
    verdict = client.post("/api/validate", json=bad).json()
    assert verdict["valid"] is False
    assert "sum" in verdict["error"]


def test_schema_endpoint(client):
    schema = client.get("/api/schema").json()
    assert "roth_401k" in schema["account_types"]
    assert schema["goal_types"] == ["retirement_income", "target_amount"]
    assert schema["asset_classes"] == ["stocks", "bonds", "cash"]
    assert schema["market_methods"] == ["parametric", "student_t", "bootstrap", "all"]
    assert schema["market_defaults"]["method"] == "parametric"
    assert schema["market_defaults"]["inflation"]["mean"] == 0.025
    assert schema["market_defaults"]["bootstrap"]["recenter"] is False


def test_simulate_payload(client, example_income):
    payload, progress = run_simulate(client, config=example_income, n_sims=400, seed=7)

    # Progress streams a leading 0, then rises to a final 1.0.
    assert progress[0] == 0.0
    assert progress[-1] == pytest.approx(1.0)
    assert progress == sorted(progress)

    assert payload["n_sims"] == 400
    assert 0.0 < payload["success_probability"] < 1.0
    ages = payload["ages"]
    assert ages[0] == 35 and ages[-1] == 95

    bands = payload["bands"]["real"]
    assert len(bands["p50"]) == len(ages)
    assert all(a <= b for a, b in zip(bands["p10"], bands["p50"]))
    assert all(a <= b for a, b in zip(bands["p50"], bands["p90"]))

    hist = payload["histogram"]["real"]
    assert len(hist["bin_edges"]) == len(hist["counts"]) + 1
    # Clipped paths are clamped into the last bin, so counts already include them.
    assert sum(hist["counts"]) + hist["n_failed"] == 400
    assert payload["histogram"]["at"] == "death"

    labels = [m["label"] for m in payload["markers"]]
    assert labels == ["retirement", "social security"]
    assert [t["age"] for t in payload["tables"]] == [62, 95]


def test_simulate_invalid_config_422(client):
    response = client.post("/api/simulate", json={"config": {"person": {}}})
    assert response.status_code == 422


def test_clamp_n_sims_caps_both_paths(example_income):
    config = build_config(example_income)
    # An override above the cap is clamped.
    assert _clamp_n_sims(10_000_000, config) == MAX_N_SIMS
    # Reasonable values pass through untouched.
    assert _clamp_n_sims(500, config) == 500
    # A config that smuggles a huge value in (no override) is capped too.
    smuggled = build_config({**example_income, "simulation": {"n_sims": 10_000_000}})
    assert _clamp_n_sims(None, smuggled) == MAX_N_SIMS


def test_simulate_clamps_oversized_n_sims(client, example_income, monkeypatch):
    # A hostile n_sims must not size the numpy arrays; it is capped, and the
    # payload reports the clamped value rather than OOMing. Patch the cap low
    # so the test doesn't actually run the real 150k-path simulation.
    monkeypatch.setattr("retirement_sim.web.MAX_N_SIMS", 300)
    payload, _ = run_simulate(client, config=example_income, n_sims=10_000_000, seed=1)
    assert payload["n_sims"] == 300
