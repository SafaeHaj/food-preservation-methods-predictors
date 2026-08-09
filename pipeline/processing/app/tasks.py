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
from shared.db.models import Job, Paper
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


@celery_app.task(name="processing.ingest_papers", bind=True)
def run_batch_ingestion(self, paper_ids: list, project_id: int, job_id: int) -> dict:
    """Ingest many papers under one job, each in its own transaction.

    Not a chord over `run_paper_ingestion`: a corpus ingested in parallel would make N
    concurrent model calls, and the free-tier rate limits this pipeline targets are per
    key, not per worker. Sequential inside one task also means one job row to follow
    instead of a hundred, which is what the progress stream can actually display.

    A paper that fails costs itself. The batch records the reason and continues, because
    the alternative -- failing the run on paper three of a hundred -- discards ninety-seven
    papers' worth of model calls that had already succeeded.
    """
    from app.services import ingestion

    db = SessionLocal()
    progress = JobProgressReporter(SessionLocal, job_id)
    succeeded, failed = [], []
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.warning("Batch ingestion %s: job no longer exists; skipping", job_id)
            return {"status": "skipped"}

        with unit_of_work(db):
            job.status = "running"
            job.started_at = datetime.utcnow()
            job.total_steps = len(paper_ids)

        for position, paper_id in enumerate(paper_ids, start=1):
            paper = db.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                failed.append({"paper_id": paper_id, "reason": "paper no longer exists"})
                continue

            progress.update(
                progress=int(100 * (position - 1) / len(paper_ids)),
                step=f"Ingesting {paper.original_name} ({position}/{len(paper_ids)})",
            )
            try:
                with unit_of_work(db):
                    result = ingestion.run(db, paper, job.id, progress)
                    paper.status = "extracted"
                succeeded.append({
                    "paper_id": paper_id,
                    "experiments": result.get("experiments", 0),
                    "measurements": result.get("measurements", 0),
                })
            except Exception as exc:
                logger.exception("Batch ingestion %s: paper %s failed", job_id, paper_id)
                db.rollback()
                with unit_of_work(db):
                    paper.status = "error"
                    paper.error_message = str(exc)[:ERROR_MESSAGE_CHARS]
                failed.append({"paper_id": paper_id, "reason": str(exc)[:ERROR_MESSAGE_CHARS]})

        summary = {
            "papers": len(paper_ids),
            "succeeded": len(succeeded),
            "failed": len(failed),
            "experiments": sum(item["experiments"] for item in succeeded),
            "measurements": sum(item["measurements"] for item in succeeded),
            "failures": failed,
        }
        with unit_of_work(db):
            # `partial_success` is the honest status when some papers landed and others did
            # not: "completed" would hide the failures and "failed" would hide the data.
            job.status = "completed" if not failed else (
                "partial_success" if succeeded else "failed")
            job.progress = 100
            job.current_step = (f"Done — {len(succeeded)}/{len(paper_ids)} papers, "
                                f"{summary['measurements']} measurements")
            job.completed_at = datetime.utcnow()
            job.result = summary
        return {"status": job.status, **summary}
    finally:
        db.close()


@celery_app.task(name="processing.ingest_paper", bind=True)
def run_paper_ingestion(self, paper_id: int, project_id: int, job_id: int) -> dict:
    """Gated package -> review -> normalise -> Gold -> the scientific schema.

    The two model calls live here, and neither is asked for a number: one names the axis
    column of a table the gate could not key, the other reads `treatment` and `weight_g`
    out of the methods prose.
    """
    from app.services import ingestion

    db = SessionLocal()
    progress = JobProgressReporter(SessionLocal, job_id)
    try:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        job = db.query(Job).filter(Job.id == job_id).first()
        if not paper or not job:
            logger.warning("Ingestion %s: paper or job no longer exists; skipping", job_id)
            return {"status": "skipped"}

        with unit_of_work(db):
            job.status = "running"
            job.started_at = datetime.utcnow()
            paper.status = "ingesting"

        try:
            with unit_of_work(db):
                result = ingestion.run(db, paper, job.id, progress)

            with unit_of_work(db):
                job.status = "completed"
                job.progress = 100
                job.current_step = result.pop("_step", "Done")
                job.completed_at = datetime.utcnow()
                job.result = result
                paper.status = "extracted"
            return {"status": "completed", **result}

        except Exception as exc:
            logger.exception("Ingestion %s failed for paper %s", job_id, paper_id)
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
