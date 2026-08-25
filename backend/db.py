"""
SQLite persistence for user accounts. This is the only stateful storage in the
project -- model artifacts stay on disk as files and are never written here.

The database file lives at backend/storage/shelf_life.db and is created on
first import. Nothing in the prediction/modeling path touches this module.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent
STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", BACKEND_DIR / "storage"))
AVATAR_DIR = STORAGE_DIR / "avatars"
DB_PATH = STORAGE_DIR / "shelf_life.db"

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
AVATAR_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")

# check_same_thread=False is required because FastAPI serves requests from a
# thread pool; each request still gets its own Session via get_db().
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one Session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from backend.auth import models  # noqa: F401 -- registers tables on Base

    Base.metadata.create_all(bind=engine)
