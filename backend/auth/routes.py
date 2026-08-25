"""
Auth endpoints. Mounted under /api/auth by backend/main.py.

The session cookie is set server-side as httpOnly, so the frontend never holds
a token in JS -- it just calls these endpoints with credentials included and
reads /api/auth/me to learn who it is.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth.deps import current_user, optional_user, to_user_out
from backend.auth.models import User
from backend.auth.schemas import (
    LoginRequest,
    PasswordChangeRequest,
    ProfileUpdateRequest,
    SignupRequest,
    UserOut,
)
from backend.auth.security import (
    SESSION_COOKIE,
    SESSION_DAYS,
    create_session_token,
    hash_password,
    needs_rehash,
    normalize_email,
    validate_password_strength,
    verify_password,
)
from backend.auth.storage import AvatarError, delete_avatar, save_avatar
from backend.db import AVATAR_DIR, get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Set COOKIE_SECURE=1 when serving over HTTPS. Off by default because local
# development runs on plain http://localhost and a Secure cookie would be
# silently dropped there.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"

# A valid argon2 digest of a throwaway value, used to keep login timing roughly
# constant whether or not the email exists (so the endpoint doesn't leak which
# addresses are registered).
_DUMMY_HASH = hash_password("timing-equalization-placeholder")


def _set_session_cookie(response: Response, user_id: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session_token(user_id),
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, response: Response, db: Session = Depends(get_db)) -> UserOut:
    email = normalize_email(payload.email)
    if (msg := validate_password_strength(payload.password)) is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, msg)

    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists.")

    user = User(
        email=email,
        name=payload.name.strip(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    _set_session_cookie(response, user.id)
    return to_user_out(user)


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> UserOut:
    email = normalize_email(payload.email)
    user = db.scalar(select(User).where(User.email == email))

    if user is None:
        verify_password(payload.password, _DUMMY_HASH)  # equalize timing
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
        db.commit()

    _set_session_cookie(response, user.id)
    return to_user_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut | None)
def me(user: User | None = Depends(optional_user)) -> UserOut | None:
    """Returns null rather than 401 when signed out, so the frontend can call
    this on every load to resolve session state without treating it as an error."""
    return to_user_out(user) if user else None


@router.patch("/me", response_model=UserOut)
def update_profile(
    payload: ProfileUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    if payload.name is not None:
        user.name = payload.name.strip()
    if payload.institution is not None:
        user.institution = payload.institution.strip() or None
    if payload.role is not None:
        user.role = payload.role.strip() or None
    db.commit()
    db.refresh(user)
    return to_user_out(user)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is incorrect.")
    if (msg := validate_password_strength(payload.new_password)) is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, msg)
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/me/avatar", response_model=UserOut)
async def upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    raw = await file.read()
    try:
        filename = save_avatar(raw)
    except AvatarError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    previous = user.avatar_filename
    user.avatar_filename = filename
    db.commit()
    db.refresh(user)
    delete_avatar(previous)  # only after the new one is committed
    return to_user_out(user)


@router.delete("/me/avatar", response_model=UserOut)
def remove_avatar(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> UserOut:
    previous = user.avatar_filename
    user.avatar_filename = None
    db.commit()
    db.refresh(user)
    delete_avatar(previous)
    return to_user_out(user)


@router.get("/avatar/{filename}")
def get_avatar(filename: str) -> FileResponse:
    """Serve a stored avatar. Avatars are not secret, but the path is still
    confined to AVATAR_DIR so a crafted filename can't escape the directory."""
    path = (AVATAR_DIR / filename).resolve()
    if path.parent != AVATAR_DIR.resolve() or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Avatar not found")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "private, max-age=300"})
