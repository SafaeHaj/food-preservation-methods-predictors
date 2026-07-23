from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def apply_column_migrations() -> None:
    """
    Add columns that create_all() cannot backfill on existing tables.
    Safe to call on every startup — each ALTER TABLE is wrapped in a try/except.
    Only needed for SQLite where Alembic auto-migrations are not running.
    """
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    migrations = [
        # ExtEvidence — Docling provenance anchor (added in Docling pipeline)
        "ALTER TABLE ext_evidence ADD COLUMN docling_item_ref VARCHAR",
        "ALTER TABLE ext_evidence ADD COLUMN is_chart_derived BOOLEAN DEFAULT 0",
    ]
    with engine.connect() as conn:
        for stmt in migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                # Column already exists — safe to ignore
                pass
