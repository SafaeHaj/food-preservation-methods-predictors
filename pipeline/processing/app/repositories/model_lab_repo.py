"""Queries over datasets, training runs and model results."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from shared.db.models import Job, LabModelResult, LabTrainingRun, UploadedDataset

ACTIVE_RUN_STATUSES = ("queued", "running")

#: Training runs shown in the history. Older runs stay queryable by id; the list view is a
#: recent-activity panel, not an archive.
RUN_HISTORY_LIMIT = 20


# ─── Datasets ─────────────────────────────────────────────────────────────────

def active_datasets(db: Session, project_id: int) -> list[UploadedDataset]:
    return (
        db.query(UploadedDataset)
        .filter(UploadedDataset.project_id == project_id, UploadedDataset.is_active.is_(True))
        .order_by(UploadedDataset.uploaded_at.desc())
        .all()
    )


def get_dataset(db: Session, project_id: int, dataset_id: int) -> UploadedDataset | None:
    return (
        db.query(UploadedDataset)
        .filter(
            UploadedDataset.id == dataset_id,
            UploadedDataset.project_id == project_id,
            UploadedDataset.is_active.is_(True),
        )
        .first()
    )


def find_duplicate(
    db: Session, project_id: int, file_hash: str, family: str
) -> UploadedDataset | None:
    return (
        db.query(UploadedDataset)
        .filter(
            UploadedDataset.project_id == project_id,
            UploadedDataset.file_hash == file_hash,
            UploadedDataset.dataset_family == family,
            UploadedDataset.is_active.is_(True),
        )
        .first()
    )


def active_of_family(db: Session, project_id: int, family: str) -> UploadedDataset | None:
    return (
        db.query(UploadedDataset)
        .filter(
            UploadedDataset.project_id == project_id,
            UploadedDataset.dataset_family == family,
            UploadedDataset.is_active.is_(True),
        )
        .first()
    )


# ─── Training runs ────────────────────────────────────────────────────────────

def recent_runs(db: Session, project_id: int) -> list[LabTrainingRun]:
    return (
        db.query(LabTrainingRun)
        .filter(LabTrainingRun.project_id == project_id)
        .order_by(LabTrainingRun.created_at.desc())
        .limit(RUN_HISTORY_LIMIT)
        .all()
    )


def get_run(db: Session, project_id: int, run_id: int) -> LabTrainingRun | None:
    return (
        db.query(LabTrainingRun)
        .filter(LabTrainingRun.id == run_id, LabTrainingRun.project_id == project_id)
        .first()
    )


def active_run_for_dataset(db: Session, project_id: int, dataset_id: int) -> LabTrainingRun | None:
    return (
        db.query(LabTrainingRun)
        .filter(
            LabTrainingRun.project_id == project_id,
            LabTrainingRun.dataset_id == dataset_id,
            LabTrainingRun.status.in_(ACTIVE_RUN_STATUSES),
        )
        .first()
    )


def results_by_run(db: Session, run_ids: list[int]) -> dict[int, list[LabModelResult]]:
    """All model results for many runs in one query."""
    if not run_ids:
        return {}
    grouped: dict[int, list[LabModelResult]] = {run_id: [] for run_id in run_ids}
    for result in (
        db.query(LabModelResult).filter(LabModelResult.training_run_id.in_(run_ids)).all()
    ):
        grouped[result.training_run_id].append(result)
    return grouped


def dataset_names(db: Session, dataset_ids: list[int]) -> dict[int, str]:
    if not dataset_ids:
        return {}
    return dict(
        db.query(UploadedDataset.id, UploadedDataset.original_name)
        .filter(UploadedDataset.id.in_(dataset_ids))
        .all()
    )


def jobs_by_id(db: Session, job_ids: list[int]) -> dict[int, Job]:
    if not job_ids:
        return {}
    return {job.id: job for job in db.query(Job).filter(Job.id.in_(job_ids)).all()}


# ─── Model results ────────────────────────────────────────────────────────────

def active_models(db: Session, project_id: int) -> list[LabModelResult]:
    return (
        db.query(LabModelResult)
        .filter(LabModelResult.project_id == project_id, LabModelResult.is_active.is_(True))
        .order_by(
            LabModelResult.training_run_id.desc(), LabModelResult.created_at.desc()
        )
        .all()
    )


def get_model(
    db: Session, project_id: int, model_id: int, *, active_only: bool = False
) -> LabModelResult | None:
    query = db.query(LabModelResult).filter(
        LabModelResult.id == model_id, LabModelResult.project_id == project_id
    )
    if active_only:
        query = query.filter(LabModelResult.is_active.is_(True))
    return query.first()


def placeholder_results(
    db: Session, run_id: int, project_id: int, family: str, model_names: list[str]
) -> dict[str, LabModelResult]:
    """Pre-create one pending row per engine so the UI can show live per-model status."""
    placeholders: dict[str, LabModelResult] = {}
    for name in model_names:
        result = LabModelResult(
            training_run_id=run_id,
            project_id=project_id,
            model_name=name,
            model_family=family,
            status="pending",
            is_active=True,
        )
        db.add(result)
        placeholders[name] = result
    db.flush()
    return placeholders


def get_dataset_by_id(db: Session, dataset_id: int) -> UploadedDataset | None:
    return db.query(UploadedDataset).filter(UploadedDataset.id == dataset_id).first()


def get_run_by_id(db: Session, run_id: int) -> LabTrainingRun | None:
    return db.query(LabTrainingRun).filter(LabTrainingRun.id == run_id).first()


def optional_job(db: Session, job_id: Optional[int]) -> Job | None:
    if job_id is None:
        return None
    return db.query(Job).filter(Job.id == job_id).first()
