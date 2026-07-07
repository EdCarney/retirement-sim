"""API tests for the local web server (retirement_sim.web)."""

import copy
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from retirement_sim.config import load_config
from retirement_sim.web import create_app

CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"


@pytest.fixture
def configs_dir(tmp_path):
    for name in ("example_income_goal.yaml", "example_target_amount.yaml"):
        (tmp_path / name).write_text((CONFIG_DIR / name).read_text())
    return tmp_path


@pytest.fixture
def client(configs_dir):
    return TestClient(create_app(configs_dir))


def test_list_configs(client):
    entries = client.get("/api/configs").json()
    names = [e["name"] for e in entries]
    assert names == ["example_income_goal.yaml", "example_target_amount.yaml"]
    by_name = {e["name"]: e for e in entries}
    assert by_name["example_income_goal.yaml"]["goal_type"] == "retirement_income"
    assert all(e["error"] is None for e in entries)


def test_get_config(client):
    body = client.get("/api/configs/example_income_goal.yaml").json()
    assert body["config"]["person"]["current_age"] == 35
    assert body["error"] is None
    assert "person:" in body["yaml"]


def test_get_missing_config_404(client):
    assert client.get("/api/configs/nope.yaml").status_code == 404


@pytest.mark.parametrize("name", ["../evil.yaml", "..%2Fevil.yaml", "evil.txt", ".yaml"])
def test_bad_names_rejected(client, name):
    response = client.get(f"/api/configs/{name}")
    assert response.status_code in (400, 404)  # 404 when the router rejects the path


def test_save_roundtrip_stays_cli_compatible(client, configs_dir):
    body = client.get("/api/configs/example_income_goal.yaml").json()
    raw = body["config"]
    raw["person"]["retirement_age"] = 60

    response = client.put("/api/configs/example_income_goal.yaml", json=raw)
    assert response.status_code == 200

    on_disk = yaml.safe_load((configs_dir / "example_income_goal.yaml").read_text())
    assert on_disk["person"]["retirement_age"] == 60
    config = load_config(configs_dir / "example_income_goal.yaml")
    assert config.person.retirement_age == 60


def test_save_invalid_config_422_with_message(client, configs_dir):
    raw = client.get("/api/configs/example_income_goal.yaml").json()["config"]
    original = (configs_dir / "example_income_goal.yaml").read_text()
    raw["person"]["death_age"] = 50  # before retirement

    response = client.put("/api/configs/example_income_goal.yaml", json=raw)
    assert response.status_code == 422
    assert "retirement_age" in response.json()["detail"]
    # Invalid saves must not touch the file.
    assert (configs_dir / "example_income_goal.yaml").read_text() == original


def test_create_delete_and_copy(client, configs_dir):
    created = client.post("/api/configs/new_plan.yaml")
    assert created.status_code == 201
    assert load_config(configs_dir / "new_plan.yaml")  # template is valid

    assert client.post("/api/configs/new_plan.yaml").status_code == 409

    copied = client.post("/api/configs/copy.yaml", params={"copy_from": "example_income_goal.yaml"})
    assert copied.status_code == 201
    assert copied.json()["config"]["person"]["current_age"] == 35

    assert client.delete("/api/configs/copy.yaml").status_code == 200
    assert not (configs_dir / "copy.yaml").exists()
    assert client.delete("/api/configs/copy.yaml").status_code == 404


def test_rename_config(client, configs_dir):
    response = client.post(
        "/api/configs/example_income_goal.yaml/rename", params={"to": "renamed.yaml"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "renamed.yaml"
    assert not (configs_dir / "example_income_goal.yaml").exists()
    assert load_config(configs_dir / "renamed.yaml")  # content moved intact

    # Missing source is a 404; colliding target is a 409.
    assert (
        client.post("/api/configs/gone.yaml/rename", params={"to": "x.yaml"}).status_code == 404
    )
    assert (
        client.post(
            "/api/configs/renamed.yaml/rename", params={"to": "example_target_amount.yaml"}
        ).status_code
        == 409
    )
    # An invalid target name is rejected before touching disk.
    assert (
        client.post("/api/configs/renamed.yaml/rename", params={"to": "../evil.yaml"}).status_code
        == 400
    )
    assert (configs_dir / "renamed.yaml").exists()


def test_validate_endpoint(client):
    raw = client.get("/api/configs/example_income_goal.yaml").json()["config"]
    assert client.post("/api/validate", json=raw).json() == {"valid": True, "error": None}

    bad = copy.deepcopy(raw)
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


def test_simulate_payload(client):
    raw = client.get("/api/configs/example_income_goal.yaml").json()["config"]
    response = client.post("/api/simulate", json={"config": raw, "n_sims": 400, "seed": 7})
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
