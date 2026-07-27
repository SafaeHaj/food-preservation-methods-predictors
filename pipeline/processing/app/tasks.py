"""Processing-domain Celery tasks.

Model fitting and export building run in the worker, not in a FastAPI `BackgroundTasks`
callback. A survival fit with an R-frailty second stage can run for minutes; doing that
inside the API container blocked a request worker for the duration and lost the run
entirely on restart, leaving the training run stuck at "running".
"""

from __future__ import annotations

import logging
from datetime import datetime

from shared.celery import make_celery
from shared.db.database import SessionLocal
from shared.db.models import Job, LabModelResult, LabTrainingRun
from shared.uow import JobProgressReporter, unit_of_work

logger = logging.getLogger(__name__)

celery_app = make_celery("processing")

ERROR_MESSAGE_CHARS = 500


@celery_app.task(name="processing.train_models", bind=True)
def run_training(self, run_id: int, dataset_id: int, project_id: int, job_id: int) -> dict:
    """Fit the model family for one training run."""
    from app.services import training_service

    db = SessionLocal()
    progress = JobProgressReporter(SessionLocal, job_id)
    try:
        run = db.query(LabTrainingRun).filter(LabTrainingRun.id == run_id).first()
        job = db.query(Job).filter(Job.id == job_id).first()
        if not run or not job:
            logger.warning("Training %s: run or job no longer exists; skipping", run_id)
            return {"status": "skipped"}

        with unit_of_work(db):
            run.status = "running"
            job.status = "running"
            job.started_at = datetime.utcnow()

        try:
            with unit_of_work(db):
                result = training_service.execute(db, run, progress)

            with unit_of_work(db):
                job.status = "completed"
                job.progress = 100
                job.current_step = result.pop("_step", "Done")
                job.completed_at = datetime.utcnow()
                job.result = result
            return {"status": "completed", **result}

        except Exception as exc:
            logger.exception("Training run %s failed", run_id)
            db.rollback()
            message = str(exc)[:ERROR_MESSAGE_CHARS]
            with unit_of_work(db):
                run.status = "failed"
                run.error_message = message
                run.completed_at = datetime.utcnow()
                job.status = "failed"
                job.error_message = message
                job.completed_at = datetime.utcnow()
                # The rollback discarded the placeholder rows, so nothing is left showing
                # "pending" forever -- the previous code left them behind on every failure.
                db.query(LabModelResult).filter(
                    LabModelResult.training_run_id == run_id,
                    LabModelResult.status == "pending",
                ).update({"status": "failed", "error_message": message}, synchronize_session=False)
            raise
    finally:
        db.close()


@celery_app.task(name="processing.build_export", bind=True)
def run_export(self, export_run_id: int) -> dict:
    """Materialize a requested dataset export."""
    from app.services.exporter import build_export_async

    build_export_async(export_run_id)
    return {"status": "completed", "export_run_id": export_run_id}


@celery_app.task(name="processing.fit_trajectory", bind=True)
def run_trajectory_fit(self, model_run_id: int) -> dict:
    """Fit kinetic models to one curated trajectory."""
    from app.services.model_registry import fit_trajectory_async

    fit_trajectory_async(model_run_id)
    return {"status": "completed", "model_run_id": model_run_id}
