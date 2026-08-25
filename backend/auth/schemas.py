"""Request/response shapes for the auth API. Note there is no schema that
carries a password hash outward -- UserOut is the only user representation the
API ever returns."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class ProfileUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    institution: str | None = Field(default=None, max_length=200)
    role: str | None = Field(default=None, max_length=120)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    institution: str | None = None
    role: str | None = None
    avatar_url: str | None = None
    created_at: dt.datetime
