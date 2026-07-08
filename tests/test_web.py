"""API tests for the stateless web server (retirement_sim.web)."""

import copy
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from retirement_sim.config import build_config
from retirement_sim.web import create_app

CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"


@pytest.fixture
def example_income() -> dict:
    return yaml.safe_load((CONFIG_DIR / "example_income_goal.yaml").read_text())


@pytest.fixture
def client():
    return TestClient(create_app())


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
    response = client.post(
        "/api/simulate", json={"config": example_income, "n_sims": 400, "seed": 7}
    )
    assert response.status_code == 200
    payload = response.json()

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
