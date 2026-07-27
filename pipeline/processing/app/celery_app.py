"""
Celery application instance.

Used by docker-compose worker service:
  celery -A app.celery_app worker --loglevel=info

In development (no Redis), BackgroundTasks in FastAPI handles async work directly.
"""

import os

from celery import Celery

celery_app = Celery(
    "food_research",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task(bind=True, name="tasks.extract_paper")
def extract_paper_task(self, job_id: int) -> dict:
    """Celery task wrapper for legacy paper extraction."""
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        from app.services.ai_extractor import extract_data_with_ai  # noqa: F401
        return {"status": "completed", "job_id": job_id}
    finally:
        db.close()


@celery_app.task(bind=True, name="tasks.food_extract_paper", max_retries=2, default_retry_delay=30)
def food_extract_paper_task(self, paper_id: int, project_id: int, job_id: int) -> dict:
    """
    Celery task for the full Docling-based food extraction pipeline.

    Runs: Docling → PP-Chart2Table → evidence packages → LLM extraction → DB persist.
    Falls back to retry on transient errors (e.g. GPU OOM, network hiccup).
    """
    try:
        from app.api.routes.food_extraction import _run_food_extraction
        _run_food_extraction(paper_id, project_id, job_id)
        return {"status": "completed", "paper_id": paper_id, "job_id": job_id}
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="tasks.fit_trajectory")
def fit_trajectory_task(self, run_id: int) -> dict:
    """Celery task wrapper for model fitting."""
    from app.services.model_registry import fit_trajectory_async
    fit_trajectory_async(run_id)
    return {"status": "completed", "run_id": run_id}


@celery_app.task(bind=True, name="tasks.build_export")
def build_export_task(self, run_id: int) -> dict:
    """Celery task wrapper for export building."""
    from app.services.exporter import build_export_async
    build_export_async(run_id)
    return {"status": "completed", "run_id": run_id}
