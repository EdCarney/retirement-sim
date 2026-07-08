"""Authentication primitives: password hashing, session tokens, signup gating.

Everything here is standard library — no new dependency. Passwords are hashed
with scrypt (memory-hard); sessions are opaque random tokens whose SHA-256 is
what's stored server-side (see ``retirement_sim.db``), so a database leak never
yields a usable session cookie.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

# Session lifetime and the cookie that carries the token.
SESSION_TTL = timedelta(days=14)
SESSION_COOKIE = "rsim_session"

# scrypt parameters (RFC 7914 interactive-login range). n must be a power of 2.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_LEN = 32
_SALT_BYTES = 16

# Basic input bounds, enforced at the endpoint layer.
MIN_USERNAME_LEN = 3
MAX_USERNAME_LEN = 32
MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 200


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def hash_password(password: str) -> str:
    """Hash a password into a self-describing ``scrypt$n$r$p$salt$hash`` string.

    Storing the parameters inline means ``verify_password`` needs no external
    config and the cost can be raised later without breaking old hashes.
    """
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_LEN,
        # scrypt's memory use is ~128*n*r bytes; raise maxmem above the default
        # so the OpenSSL binding doesn't reject our parameters.
        maxmem=2 * 128 * _SCRYPT_N * _SCRYPT_R,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of ``password`` against a stored hash.

    Returns ``False`` (rather than raising) on any malformed hash, so a corrupt
    row can't crash the login path.
    """
    try:
        scheme, n_s, r_s, p_s, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        n, r, p = int(n_s), int(r_s), int(p_s)
        salt = _unb64(salt_b64)
        expected = _unb64(hash_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
            maxmem=2 * 128 * n * r,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def new_session_token() -> str:
    """A fresh, unguessable session token (the raw value handed to the browser)."""
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    """SHA-256 of a session token — the form actually stored in the database."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry() -> str:
    """ISO-8601 expiry timestamp for a session created now."""
    return (datetime.now(timezone.utc) + SESSION_TTL).isoformat()


def signup_code() -> str | None:
    """The configured invite code, or ``None`` if signup is disabled."""
    code = os.environ.get("SIGNUP_CODE")
    return code or None


def signup_enabled() -> bool:
    """Whether self-service signup is open (i.e. an invite code is configured)."""
    return signup_code() is not None


def check_signup_code(supplied: str) -> bool:
    """Constant-time comparison of a supplied invite code to the configured one."""
    code = signup_code()
    if code is None:
        return False
    return hmac.compare_digest(supplied, code)


def cookie_secure() -> bool:
    """Whether the session cookie gets the ``Secure`` flag.

    Defaults on (production serves HTTPS). Local dev over plain HTTP must set
    ``COOKIE_SECURE=0`` or the browser silently drops the cookie and login never
    "sticks".
    """
    return os.environ.get("COOKIE_SECURE", "1") != "0"
