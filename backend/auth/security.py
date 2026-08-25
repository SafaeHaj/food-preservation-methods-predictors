"""
Password hashing and session tokens.

Passwords: argon2id (argon2-cffi defaults -- memory-hard, the current OWASP
recommendation). Verification transparently re-hashes when parameters change.

Sessions: a signed JWT carried in an httpOnly cookie. httpOnly means page
JavaScript cannot read it, so an XSS bug cannot exfiltrate the session; SameSite
blocks it from riding along on cross-site requests.
"""
from __future__ import annotations

import datetime as dt
import os
import secrets
from pathlib import Path

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from backend.db import STORAGE_DIR

ALGORITHM = "HS256"
SESSION_COOKIE = "shelf_life_session"
SESSION_DAYS = 7

_hasher = PasswordHasher()


def _load_secret_key() -> str:
    """Prefer SECRET_KEY from the environment. For local development, fall back
    to a random key persisted under the storage dir so restarting the server
    doesn't silently log everyone out. Never ship a hardcoded default."""
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    key_file = STORAGE_DIR / ".session_secret"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    generated = secrets.token_urlsafe(48)
    key_file.write_text(generated, encoding="utf-8")
    try:  # best effort: owner-only on POSIX, no-op on Windows
        key_file.chmod(0o600)
    except OSError:
        pass
    return generated


SECRET_KEY = _load_secret_key()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, ValueError):
        return False


def create_session_token(user_id: str) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + dt.timedelta(days=SESSION_DAYS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def read_session_token(token: str) -> str | None:
    """Return the user id, or None if the token is invalid/expired/tampered."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) else None


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_password_strength(password: str) -> str | None:
    """Return an error message, or None when acceptable. Deliberately simple
    and length-led rather than a composition-rules checklist."""
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if len(password) > 200:
        return "Password must be at most 200 characters."
    if password.strip() == "":
        return "Password cannot be blank."
    return None
