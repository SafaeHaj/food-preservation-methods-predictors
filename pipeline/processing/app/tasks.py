"""Processing-domain Celery tasks.

Dataset builds run here, in the worker, not in a FastAPI `BackgroundTasks` callback. A
build reads every measurement in a project and will hand the result to the prediction
service, which can legitimately take minutes; doing that inside the API container blocked a
request worker for the duration and lost the run entirely on restart, leaving the job stuck
at "running".

The task is real even though `dataset_builder.build` is still a stub: the lifecycle around
it -- mark running, one transaction, record the outcome, fail loudly with a reason -- is
what would otherwise have to be rediscovered when the builder lands.
"""

from __future__ import annotations

import logging
from datetime import datetime

from shared.celery import make_celery
from shared.db.database import SessionLocal
from shared.db.models import Job
from shared.uow import JobProgressReporter, unit_of_work

logger = logging.getLogger(__name__)

celery_app = make_celery("processing")

#: How much of an exception message is worth keeping on the job row. Enough to identify the
#: failure; the full traceback is in the worker log, keyed by the same job id.
ERROR_MESSAGE_CHARS = 500


@celery_app.task(name="processing.build_dataset", bind=True)
def run_dataset_build(self, project_id: int, job_id: int) -> dict:
    """Flatten a project's scientific tables into a prediction-ready dataset."""
    from app.services import dataset_builder

    db = SessionLocal()
    progress = JobProgressReporter(SessionLocal, job_id)
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.warning("Dataset build %s: job no longer exists; skipping", job_id)
            return {"status": "skipped"}

        with unit_of_work(db):
            job.status = "running"
            job.started_at = datetime.utcnow()
            job.current_step = "Reading the scientific tables"

        try:
            with unit_of_work(db):
                preview = dataset_builder.build(db, project_id, progress)

            result = {
                "status": preview.status,
                "row_count": preview.row_count,
                "columns": preview.columns,
                "source": preview.source.model_dump(),
            }
            with unit_of_work(db):
                job.status = "completed"
                job.progress = 100
                job.current_step = (
                    "Dataset builder is not implemented yet"
                    if preview.status == "not_implemented"
                    else "Done"
                )
                job.completed_at = datetime.utcnow()
                job.result = result
            return {"status": "completed", **result}

        except Exception as exc:
            logger.exception("Dataset build failed for project %s", project_id)
            db.rollback()
            with unit_of_work(db):
                job.status = "failed"
                job.error_message = str(exc)[:ERROR_MESSAGE_CHARS]
                job.completed_at = datetime.utcnow()
            raise
    finally:
        db.close()
