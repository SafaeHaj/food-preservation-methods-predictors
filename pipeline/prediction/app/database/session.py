"""Database engine, session factory, and lifecycle helpers."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.database.models.base import Base

_settings = get_settings()
_is_sqlite = _settings.database_url.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_engine(_settings.database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


@event.listens_for(engine, "connect")
def _enable_sqlite_fk(dbapi_conn, _record) -> None:
    """SQLite ignores foreign keys unless asked, per connection."""
    if isinstance(dbapi_conn, sqlite3.Connection):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create the schema (dev/test convenience; Alembic is the migration path)."""
    import app.database.models  # noqa: F401  (register every mapper)

    _ensure_sqlite_parent()
    Base.metadata.create_all(bind=engine)


def _ensure_sqlite_parent() -> None:
    """Make sure the SQLite file's directory exists before create_all."""
    if not _is_sqlite:
        return
    db_path = _settings.database_url.split("///", 1)[-1]
    if db_path and db_path != ":memory:":
        Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
