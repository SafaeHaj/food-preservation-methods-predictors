"""Model-lab training: run creation, execution and reporting.

Split out of the route module, where `_bg_train` was a 180-line function containing both
model families inline, opening its own session, and reporting failure through a `_fail`
helper that inspected `dir()` to find out which locals had been bound.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from shared.config import get_processing_settings
from shared.db.models import Job, LabModelResult, LabTrainingRun, UploadedDataset
from shared.errors import BusinessRuleError, ConflictError, NotFoundError
from shared.uow import JobProgressReporter, unit_of_work

from app.repositories import model_lab_repo
from app.schemas.model_lab import (
    JobSummary, ModelResultOut, TrainingAccepted, TrainingRunOut, TrainRequest,
)
from app.services import dataset_service

logger = logging.getLogger(__name__)
_settings = get_processing_settings()

KINETIC = "kinetic"
SURVIVAL = "survival"

PROGRESS_LOAD = 10
PROGRESS_FIT = 25
PROGRESS_SAVE = 80


# ─── Serialization ────────────────────────────────────────────────────────────

def result_to_out(result: LabModelResult, *, include_results: bool = False) -> ModelResultOut:
    return ModelResultOut(
        id=result.id,
        training_run_id=result.training_run_id,
        model_name=result.model_name,
        model_family=result.model_family,
        status=result.status,
        skip_reason=result.skip_reason,
        error_message=result.error_message,
        metrics=json.loads(result.metrics_json or "{}"),
        parameters=json.loads(result.parameters_json or "{}"),
        feature_cols=json.loads(result.feature_cols_json or "[]"),
        target_col=result.target_col,
        mae=result.mae,
        rmse=result.rmse,
        r_squared=result.r_squared,
        concordance_index=result.concordance_index,
        has_artifact=bool(result.artifact_path),
        is_active=bool(result.is_active),
        created_at=result.created_at,
        completed_at=result.completed_at,
        results=json.loads(result.results_json or "{}") if include_results else None,
    )


def run_to_out(
    run: LabTrainingRun,
    results: list[LabModelResult],
    dataset_name: str | None,
    job: Job | None = None,
) -> TrainingRunOut:
    return TrainingRunOut(
        id=run.id,
        project_id=run.project_id,
        dataset_id=run.dataset_id,
        dataset_name=dataset_name,
        job_id=run.job_id,
        dataset_family=run.dataset_family,
        n_trajectories=run.n_trajectories or 0,
        n_fitted=run.n_fitted or 0,
        status=run.status,
        error_message=run.error_message,
        created_at=run.created_at,
        completed_at=run.completed_at,
        model_results=[result_to_out(result) for result in results],
        job=(
            JobSummary(
                status=job.status,
                progress=job.progress or 0,
                current_step=job.current_step or "",
                error_message=job.error_message or None,
            )
            if job
            else None
        ),
    )


# ─── Reads ────────────────────────────────────────────────────────────────────

def list_runs(db: Session, project_id: int) -> list[TrainingRunOut]:
    runs = model_lab_repo.recent_runs(db, project_id)
    results = model_lab_repo.results_by_run(db, [run.id for run in runs])
    names = model_lab_repo.dataset_names(db, [run.dataset_id for run in runs if run.dataset_id])
    jobs = model_lab_repo.jobs_by_id(db, [run.job_id for run in runs if run.job_id])

    return [
        run_to_out(
            run,
            results.get(run.id, []),
            names.get(run.dataset_id),
            jobs.get(run.job_id) if run.job_id else None,
        )
        for run in runs
    ]


def get_run(db: Session, project_id: int, run_id: int) -> TrainingRunOut:
    run = model_lab_repo.get_run(db, project_id, run_id)
    if not run:
        raise NotFoundError.for_resource("Training run", run_id)

    results = model_lab_repo.results_by_run(db, [run_id]).get(run_id, [])
    names = model_lab_repo.dataset_names(db, [run.dataset_id] if run.dataset_id else [])
    return run_to_out(
        run, results, names.get(run.dataset_id), model_lab_repo.optional_job(db, run.job_id)
    )


# ─── Starting a run ───────────────────────────────────────────────────────────

def start_training(
    db: Session, project_id: int, user_id: int, body: TrainRequest
) -> TrainingAccepted:
    from app.tasks import run_training

    dataset = dataset_service.require_dataset(db, project_id, body.dataset_id)
    if dataset.parse_status != "ready":
        raise BusinessRuleError(
            "This dataset could not be parsed; re-upload the file before training",
            details={"parse_error": dataset.parse_error},
        )
    if body.dataset_family not in (KINETIC, SURVIVAL):
        raise BusinessRuleError(
            f"'{body.dataset_family}' is not a known model family",
            details={"allowed": [KINETIC, SURVIVAL]},
        )
    if model_lab_repo.active_run_for_dataset(db, project_id, body.dataset_id):
        raise ConflictError(
            "A training run is already in progress for this dataset",
            details={"dataset_id": body.dataset_id},
        )

    with unit_of_work(db):
        dataset.column_mapping_json = json.dumps(body.column_mapping)
        dataset.dataset_family = body.dataset_family

        job = Job(
            project_id=project_id,
            job_type="training",
            status="queued",
            progress=0,
            current_step="Queued",
            created_by=user_id,
        )
        db.add(job)
        db.flush()

        run = LabTrainingRun(
            project_id=project_id,
            dataset_id=body.dataset_id,
            job_id=job.id,
            dataset_family=body.dataset_family,
            column_mapping_json=json.dumps(body.column_mapping),
            status="queued",
            created_by=user_id,
        )
        db.add(run)
        db.flush()
        run_id, job_id = run.id, job.id

    run_training.delay(run_id, body.dataset_id, project_id, job_id)
    return TrainingAccepted(training_run_id=run_id, job_id=job_id, status="queued")


# ─── Execution ────────────────────────────────────────────────────────────────

def _load_records(dataset: UploadedDataset) -> list[dict]:
    frame, _ = dataset_service.read_frame(
        Path(dataset.file_path), dataset.original_name, preview=False
    )
    return frame.to_dict("records")


def _apply_kinetic(placeholders: dict[str, LabModelResult], summary: dict) -> None:
    for name, stats in summary.items():
        result = placeholders.get(name)
        if result is None:
            continue
        converged = stats.get("n_converged", 0)
        result.status = "completed" if converged else "failed"
        result.error_message = None if converged else "No trajectories converged"
        result.metrics_json = json.dumps(
            {
                "n_converged": converged,
                "mean_mae": stats.get("mean_mae"),
                "mean_rmse": stats.get("mean_rmse"),
                "median_rmse": stats.get("median_rmse"),
                "mean_r2": stats.get("mean_r2"),
            }
        )
        result.mae = stats.get("mean_mae")
        result.rmse = stats.get("mean_rmse")
        result.r_squared = stats.get("mean_r2")
        result.completed_at = datetime.utcnow()


def _apply_survival(
    placeholders: dict[str, LabModelResult], models: dict, feature_cols: list, outcome: dict
) -> None:
    for name, model in models.items():
        result = placeholders.get(name)
        if result is None:
            continue
        status = model.get("status", "failed")
        result.status = status
        result.skip_reason = model.get("reason") if status == "skipped" else None
        result.error_message = model.get("reason") if status == "failed" else None
        result.metrics_json = json.dumps(
            {
                "concordance_index": model.get("concordance_index"),
                "n_train": model.get("n_train"),
                "n_test": model.get("n_test"),
            }
        )
        result.concordance_index = model.get("concordance_index")
        # An opaque reference the prediction service resolves; never a local path.
        result.artifact_path = model.get("artifact_path")
        result.feature_cols_json = json.dumps(feature_cols)
        result.target_col = outcome.get("time_col")
        result.event_col = outcome.get("event_col")
        result.completed_at = datetime.utcnow()


def execute(db: Session, run: LabTrainingRun, progress: JobProgressReporter) -> dict:
    """Fit the run's model family. Runs inside the caller's transaction."""
    from app.services.kinetic_trainer import run_kinetic_training
    from app.services.survival_trainer import run_survival_training

    dataset = model_lab_repo.get_dataset_by_id(db, run.dataset_id)
    if not dataset:
        raise NotFoundError.for_resource("Dataset", run.dataset_id)

    progress.update(progress=PROGRESS_LOAD, step="Loading dataset")
    records = _load_records(dataset)
    mapping = json.loads(run.column_mapping_json or "{}")

    is_kinetic = run.dataset_family == KINETIC
    names = _settings.KINETIC_MODELS if is_kinetic else _settings.SURVIVAL_MODELS
    placeholders = model_lab_repo.placeholder_results(
        db, run.id, run.project_id, run.dataset_family, names
    )

    progress.update(
        progress=PROGRESS_FIT,
        step=f"Fitting {len(names)} {run.dataset_family} model(s)",
    )

    if is_kinetic:
        outcome = run_kinetic_training(records, mapping)
    else:
        outcome = run_survival_training(records, mapping)

    progress.update(progress=PROGRESS_SAVE, step="Saving model results")

    if is_kinetic:
        run.n_trajectories = outcome.get("n_trajectories", 0)
        run.n_fitted = outcome.get("n_fitted", 0)
        _apply_kinetic(placeholders, outcome.get("summary", {}))
        for name, result in placeholders.items():
            result.results_json = json.dumps(
                {
                    "trajectories": [
                        {
                            "trajectory_id": trajectory["trajectory_id"],
                            "n_obs": trajectory["n_obs"],
                            "fit": trajectory["models"].get(name, {}),
                        }
                        for trajectory in outcome.get("trajectories", [])
                    ]
                }
            )
    else:
        _apply_survival(
            placeholders, outcome.get("models", {}), outcome.get("feature_cols", []), outcome
        )

    run.status = "completed"
    run.completed_at = datetime.utcnow()

    completed = sum(1 for result in placeholders.values() if result.status == "completed")
    return {
        "training_run_id": run.id,
        "models_completed": completed,
        "models_total": len(names),
        "_step": f"Done — {completed}/{len(names)} models fitted",
    }
