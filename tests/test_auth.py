"""Tests for username/password auth: signup gating, login, sessions."""

from datetime import datetime, timedelta, timezone

import pytest

from retirement_sim import auth
from retirement_sim.db import Database


def test_password_hash_roundtrip():
    stored = auth.hash_password("correct horse")
    assert auth.verify_password("correct horse", stored)
    assert not auth.verify_password("wrong horse", stored)
    # A random salt means two hashes of the same password differ.
    assert stored != auth.hash_password("correct horse")


def test_verify_rejects_malformed_hash():
    assert not auth.verify_password("anything", "not-a-real-hash")
    assert not auth.verify_password("anything", "")


def test_signup_success_sets_session(client_factory):
    from conftest import signup

    c = client_factory()
    resp = signup(c)
    assert resp.status_code == 200
    assert resp.json() == {"user": {"id": 1, "username": "alice"}}
    # The session cookie now authenticates subsequent calls.
    assert c.get("/api/auth/me").json() == {"user": {"id": 1, "username": "alice"}}


def test_signup_requires_correct_invite_code(client_factory):
    from conftest import signup

    c = client_factory()
    assert signup(c, code="nope").status_code == 403
    # And a wrong code leaves the caller unauthenticated.
    assert c.get("/api/auth/me").status_code == 401


def test_signup_disabled_when_code_unset(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from retirement_sim.web import create_app

    monkeypatch.delenv("SIGNUP_CODE", raising=False)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    c = TestClient(create_app(db_path=tmp_path / "app.db"))
    assert c.get("/api/auth/config").json() == {"signup_enabled": False}
    resp = c.post(
        "/api/auth/signup",
        json={"username": "alice", "password": "password123", "invite_code": ""},
    )
    assert resp.status_code == 403


def test_signup_rejects_duplicate_username_case_insensitive(client_factory):
    from conftest import signup

    c = client_factory()
    assert signup(c, username="alice").status_code == 200
    assert signup(client_factory(), username="ALICE").status_code == 409


@pytest.mark.parametrize(
    "username,password,field",
    [
        ("ab", "password123", "username"),  # too short
        ("x" * 33, "password123", "username"),  # too long
        ("alice", "short", "password"),  # too short
    ],
)
def test_signup_validates_credentials(client_factory, username, password, field):
    c = client_factory()
    resp = c.post(
        "/api/auth/signup",
        json={"username": username, "password": password, "invite_code": "test-code"},
    )
    assert resp.status_code == 400
    assert field in resp.json()["detail"]


def test_login_success_and_generic_failure(client_factory):
    from conftest import signup

    signup(client_factory())  # create alice on the shared DB

    fresh = client_factory()
    # Wrong password and unknown user return the same generic 401.
    bad_pw = fresh.post("/api/auth/login", json={"username": "alice", "password": "nope"})
    unknown = fresh.post("/api/auth/login", json={"username": "ghost", "password": "password123"})
    assert bad_pw.status_code == unknown.status_code == 401
    assert bad_pw.json()["detail"] == unknown.json()["detail"]

    ok = fresh.post("/api/auth/login", json={"username": "alice", "password": "password123"})
    assert ok.status_code == 200
    assert fresh.get("/api/auth/me").json()["user"]["username"] == "alice"


def test_logout_invalidates_session(client_factory):
    from conftest import signup

    c = client_factory()
    signup(c)
    assert c.get("/api/auth/me").status_code == 200
    assert c.post("/api/auth/logout").json() == {"ok": True}
    assert c.get("/api/auth/me").status_code == 401


def test_garbage_cookie_is_unauthenticated(client_factory):
    c = client_factory()
    c.cookies.set(auth.SESSION_COOKIE, "not-a-real-token")
    assert c.get("/api/auth/me").status_code == 401


def test_expired_session_is_rejected(client_factory, tmp_path):
    from conftest import signup

    c = client_factory()
    signup(c)
    # Backdate the session's expiry directly in the DB and confirm it's dead.
    db = Database(tmp_path / "app.db")
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with db._lock:
        db._conn.execute("UPDATE sessions SET expires_at = ?", (past,))
        db._conn.commit()
    assert c.get("/api/auth/me").status_code == 401
