"""Transaction boundary helpers.

Two distinct needs, deliberately kept apart:

`unit_of_work` marks one atomic business operation. Commit once at the end, roll back on
any exception. This replaces the previous style of committing after each individual write,
which left partially-applied work behind whenever a later step failed -- the canonical
promoter committed inside its per-paper loop, so a failure on paper 7 left papers 1-6
promoted and no record of it.

`JobProgressReporter` is the deliberate exception. A long-running job must publish progress
*while* its transaction is still open, so it uses its own short-lived session per update.
Progress is observational, not part of the business transaction; conflating the two is why
the extraction pipeline had to commit ten times mid-run.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@contextmanager
def unit_of_work(db: Session) -> Iterator[Session]:
    """Commit on success, roll back on any exception, and re-raise.

    The caller keeps ownership of the session's lifetime (FastAPI's `get_db` closes it);
    this only owns the transaction.
    """
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise


@contextmanager
def session_scope(session_factory: Callable[[], Session]) -> Iterator[Session]:
    """`unit_of_work` for code that owns its session too -- Celery tasks and scripts."""
    db = session_factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


class JobProgressReporter:
    """Publishes job progress on its own session, independent of the work transaction.

    Deliberately swallows its own failures: a dropped progress update must never abort the
    extraction or training run it is merely narrating. Failures are logged, not raised.
    """

    def __init__(self, session_factory: Callable[[], Session], job_id: int) -> None:
        self._session_factory = session_factory
        self.job_id = job_id

    def update(self, *, progress: int | None = None, step: str | None = None, **fields: Any) -> None:
        from shared.db.models import Job  # local import: avoids a models <-> uow cycle

        try:
            with session_scope(self._session_factory) as db:
                job = db.query(Job).filter(Job.id == self.job_id).first()
                if not job:
                    return
                if progress is not None:
                    job.progress = progress
                if step is not None:
                    job.current_step = step
                for key, value in fields.items():
                    setattr(job, key, value)
        except Exception:
            logger.warning("Could not publish progress for job %s", self.job_id, exc_info=True)
