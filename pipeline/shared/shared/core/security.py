"""Password hashing and JWT issue/verify."""

from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from shared.config import get_common_settings

_settings = get_common_settings()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    # A malformed stored hash must read as "wrong password", not as a 500.
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + (
        expires_delta or timedelta(minutes=_settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return jwt.encode(to_encode, _settings.SECRET_KEY, algorithm=_settings.ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Return the claims, or None if the token is invalid or expired."""
    try:
        return jwt.decode(token, _settings.SECRET_KEY, algorithms=[_settings.ALGORITHM])
    except JWTError:
        return None
