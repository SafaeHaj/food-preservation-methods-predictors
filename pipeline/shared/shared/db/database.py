"""Engine, session factory and the FastAPI session dependency.

The schema is owned by Alembic (`pipeline/shared/alembic`), applied by the gateway before
it serves. There is no `create_all` and no runtime ALTER TABLE patching: both raced the
migrations and let the live schema drift from the migration history.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from shared.config import get_common_settings

_settings = get_common_settings()

# SQLite's default thread check rejects the session being used from a Celery worker thread.
_connect_args = {"check_same_thread": False} if _settings.is_sqlite else {}

engine = create_engine(
    _settings.DATABASE_URL,
    connect_args=_connect_args,
    # Recycle before typical proxy/database idle timeouts so a pooled connection that was
    # closed server-side surfaces as a reconnect rather than a mid-request failure.
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Request-scoped session. Transactions are managed by `shared.uow.unit_of_work`."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
