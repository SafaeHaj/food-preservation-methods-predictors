"""Shared dependency injections for the API layer."""

from __future__ import annotations

from app.database.session import get_db

__all__ = ["get_db"]
