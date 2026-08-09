"""Extraction-domain Celery tasks.

Every long-running pipeline runs here, in the worker, rather than in a FastAPI
`BackgroundTasks` callback inside the API container. The worker containers were already
declared in docker-compose and already idle; meanwhile a Docling parse or an LLM call
occupied an API process for minutes, and a restart or deploy silently dropped in-flight
work with the job row left stuck at "running" forever.

Every task follows the same shape, defined once in `_run_job`:
  * resolve the paper and job, or exit quietly if either has been deleted;
  * mark running, do the work in one transaction, mark completed with a result;
  * on any exception, mark the job and paper failed, with the reason recorded.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from shared.celery import make_celery
from shared.db.database import SessionLocal
from shared.db.models import Job, Paper
from shared.uow import JobProgressReporter, unit_of_work

logger = logging.getLogger(__name__)

celery_app = make_celery("extraction")

#: How much of an exception message is worth keeping on the job row. Enough to identify the
#: failure; the full traceback is in the worker log, keyed by the same job id.
ERROR_MESSAGE_CHARS = 500


def _run_job(
    paper_id: int,
    job_id: int,
    work: Callable[[Session, Paper, Job, JobProgressReporter], dict],
) -> dict:
    """Shared job lifecycle: mark running, run `work`, record the outcome."""
    db = SessionLocal()
    progress = JobProgressReporter(SessionLocal, job_id)
    try:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        job = db.query(Job).filter(Job.id == job_id).first()
        if not paper or not job:
            logger.warning("Job %s: paper or job no longer exists; skipping", job_id)
            return {"status": "skipped"}

        with unit_of_work(db):
            job.status = "running"
            job.started_at = datetime.utcnow()
            paper.status = "extracting"

        try:
            with unit_of_work(db):
                result = work(db, paper, job, progress)

            with unit_of_work(db):
                job.status = "completed"
                job.progress = 100
                job.current_step = result.pop("_step", "Done")
                job.completed_at = datetime.utcnow()
                job.result = result
                paper.status = "extracted"
            return {"status": "completed", **result}

        except Exception as exc:
            logger.exception("Job %s failed for paper %s", job_id, paper_id)
            db.rollback()
            with unit_of_work(db):
                job.status = "failed"
                job.error_message = str(exc)[:ERROR_MESSAGE_CHARS]
                job.completed_at = datetime.utcnow()
                paper.status = "error"
                paper.error_message = str(exc)[:ERROR_MESSAGE_CHARS]
            raise
    finally:
        db.close()


@celery_app.task(name="extraction.workspace_extraction", bind=True)
def run_workspace_extraction(self, paper_id: int, project_id: int, job_id: int) -> dict:
    """Parse, convert charts, and gate: everything that needs the PDF or the GPU.

    Ends by staging the Silver package -- the gated assets with their observations -- which
    the ingestion task picks up. Splitting there is what keeps the expensive vision work
    from being repeated when a paper is re-ingested after a vocabulary change.
    """
    from app.services import docling_pipeline

    def work(db: Session, paper: Paper, job: Job, progress: JobProgressReporter) -> dict:
        outcome = docling_pipeline.run(db, paper, job.id, progress)
        return {
            **outcome.as_dict(),
            "_step": (
                f"Done — {outcome.gated_tables} tables and {outcome.gated_figures} figures "
                f"hold data ({outcome.observations} observations)"
            ),
        }

    return _run_job(paper_id, job_id, work)
