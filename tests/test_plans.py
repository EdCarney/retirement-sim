"""Tests for per-user plan storage CRUD and cross-user isolation."""

from conftest import signup

PLAN = {"id": "p1", "name": "My Plan", "config": {"person": {"current_age": 30}}}


def test_plan_crud_roundtrip(client_factory):
    c = client_factory()
    signup(c)

    assert c.get("/api/plans").json() == []

    created = c.post("/api/plans", json=PLAN)
    assert created.status_code == 201
    assert created.json() == PLAN

    listed = c.get("/api/plans").json()
    assert listed == [PLAN]

    updated = c.put(
        "/api/plans/p1", json={"name": "Renamed", "config": {"person": {"current_age": 31}}}
    )
    assert updated.status_code == 200
    assert updated.json() == {
        "id": "p1",
        "name": "Renamed",
        "config": {"person": {"current_age": 31}},
    }

    assert c.delete("/api/plans/p1").status_code == 204
    assert c.get("/api/plans").json() == []


def test_plans_require_auth(client_factory):
    c = client_factory()  # never logs in
    assert c.get("/api/plans").status_code == 401
    assert c.post("/api/plans", json=PLAN).status_code == 401


def test_users_cannot_touch_each_others_plans(client_factory):
    alice = client_factory()
    signup(alice, username="alice")
    alice.post("/api/plans", json=PLAN)

    bob = client_factory()
    signup(bob, username="bob")

    # Bob sees none of alice's plans, and can't update or delete them.
    assert bob.get("/api/plans").json() == []
    assert bob.put("/api/plans/p1", json={"name": "x", "config": {}}).status_code == 404
    assert bob.delete("/api/plans/p1").status_code == 404

    # Alice's plan is untouched.
    assert alice.get("/api/plans").json() == [PLAN]


def test_update_and_delete_missing_plan_404(client_factory):
    c = client_factory()
    signup(c)
    assert c.put("/api/plans/ghost", json={"name": "x", "config": {}}).status_code == 404
    assert c.delete("/api/plans/ghost").status_code == 404


def test_duplicate_plan_id_conflicts(client_factory):
    c = client_factory()
    signup(c)
    assert c.post("/api/plans", json=PLAN).status_code == 201
    assert c.post("/api/plans", json=PLAN).status_code == 409


def test_oversized_config_rejected(client_factory):
    c = client_factory()
    signup(c)
    huge = {"id": "big", "name": "big", "config": {"blob": "x" * 1_100_000}}
    assert c.post("/api/plans", json=huge).status_code == 413
