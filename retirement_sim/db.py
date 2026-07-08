"""SQLite persistence for user accounts and their saved plans.

This is the app's first server-side state. It deliberately stays tiny: a single
connection guarded by one lock, serving a single-instance deployment (Azure App
Service, one worker). The database file lives on the persistent ``/home`` volume
in production (see ``default_db_path``); scaling beyond one instance is **not**
supported — several containers writing one SQLite file over Azure Files (SMB)
would corrupt it.

Design notes:

* One ``sqlite3.Connection`` opened with ``check_same_thread=False`` and shared
  across FastAPI's threadpool, with every access serialized through a single
  ``threading.Lock``. Writes here are tiny and infrequent (saving a plan), so a
  global lock is both correct and more than fast enough.
* The default rollback journal is kept — **not** WAL — because WAL is unsafe over
  the SMB-mounted ``/home`` share. ``busy_timeout`` smooths over brief contention.
* Every plan/session query is scoped by ``user_id`` so one user can never read or
  mutate another's rows.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def default_db_path() -> Path:
    """Where the SQLite file lives, honoring env overrides.

    ``DB_PATH`` names the file directly; otherwise it's ``app.db`` under
    ``DATA_DIR`` (``/home/data`` in the container, a repo-local ``.data`` dir in
    dev). Resolved lazily so tests can point it at a ``tmp_path``.
    """
    explicit = os.environ.get("DB_PATH")
    if explicit:
        return Path(explicit)
    data_dir = os.environ.get("DATA_DIR") or str(_REPO_ROOT / ".data")
    return Path(data_dir) / "app.db"


def _now() -> str:
    """Current UTC time as an ISO-8601 string (the storage format for times)."""
    return datetime.now(timezone.utc).isoformat()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS plans (
    id         TEXT NOT NULL,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    config     TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, id)
);
"""


class Database:
    """Owns the SQLite connection and every query, serialized under one lock."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # check_same_thread=False: FastAPI runs sync endpoints on a threadpool,
        # so the connection is touched from multiple threads. The lock below —
        # not per-thread connections — provides the required serialization.
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.execute("PRAGMA foreign_keys = ON")
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ── users ────────────────────────────────────────────────────────────────

    def create_user(self, username: str, password_hash: str) -> sqlite3.Row:
        """Insert a user, returning the created row.

        Raises ``sqlite3.IntegrityError`` if the username is taken (the caller
        maps this to a 409).
        """
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, _now()),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM users WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
        return row

    def get_user_by_username(self, username: str) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
            ).fetchone()

    def get_user_by_id(self, user_id: int) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()

    # ── sessions ─────────────────────────────────────────────────────────────

    def create_session(self, user_id: int, token_hash: str, expires_at: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (token_hash, user_id, _now(), expires_at),
            )
            self._conn.commit()

    def get_session_user(self, token_hash: str) -> sqlite3.Row | None:
        """Return the user for a live (unexpired) session, or ``None``.

        Joins straight to the user so a valid session yields the account in one
        call; expired rows are treated as absent.
        """
        with self._lock:
            return self._conn.execute(
                "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash = ? AND s.expires_at > ?",
                (token_hash, _now()),
            ).fetchone()

    def delete_session(self, token_hash: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (token_hash,)
            )
            self._conn.commit()

    def delete_expired_sessions(self) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM sessions WHERE expires_at <= ?", (_now(),)
            )
            self._conn.commit()

    # ── plans ────────────────────────────────────────────────────────────────

    def list_plans(self, user_id: int) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(
                "SELECT id, name, config FROM plans WHERE user_id = ? ORDER BY updated_at",
                (user_id,),
            ).fetchall()

    def count_plans(self, user_id: int) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM plans WHERE user_id = ?", (user_id,)
            ).fetchone()[0]

    def get_plan(self, user_id: int, plan_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(
                "SELECT id, name, config FROM plans WHERE user_id = ? AND id = ?",
                (user_id, plan_id),
            ).fetchone()

    def create_plan(
        self, user_id: int, plan_id: str, name: str, config_json: str
    ) -> None:
        """Insert a plan. Raises ``sqlite3.IntegrityError`` on duplicate id."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO plans (id, user_id, name, config, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (plan_id, user_id, name, config_json, _now()),
            )
            self._conn.commit()

    def update_plan(
        self, user_id: int, plan_id: str, name: str, config_json: str
    ) -> bool:
        """Update a plan in place. Returns ``False`` if the user owns no such id."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE plans SET name = ?, config = ?, updated_at = ? "
                "WHERE user_id = ? AND id = ?",
                (name, config_json, _now(), user_id, plan_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def delete_plan(self, user_id: int, plan_id: str) -> bool:
        """Delete a plan. Returns ``False`` if the user owns no such id."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM plans WHERE user_id = ? AND id = ?", (user_id, plan_id)
            )
            self._conn.commit()
            return cur.rowcount > 0
