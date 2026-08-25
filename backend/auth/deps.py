"""Request-scoped auth dependencies."""
from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.auth.models import User
from backend.auth.schemas import UserOut
from backend.auth.security import SESSION_COOKIE, read_session_token
from backend.db import get_db


def optional_user(
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> User | None:
    """Resolve the signed-in user, or None. Use for endpoints that work either
    way; use current_user to require a session."""
    if not session:
        return None
    user_id = read_session_token(session)
    if not user_id:
        return None
    return db.get(User, user_id)


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user


def to_user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        institution=user.institution,
        role=user.role,
        avatar_url=f"/api/auth/avatar/{user.avatar_filename}" if user.avatar_filename else None,
        created_at=user.created_at,
    )
