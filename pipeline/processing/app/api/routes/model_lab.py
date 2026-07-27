"""
Model Lab API routes.

Handles:
  - Dataset upload, persistence, column-mapping, replace, delete, download
  - Training job creation and status polling
  - Trained model registry
  - Prediction
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings, UPLOAD_PATH
from app.db.database import SessionLocal, get_db
from app.db.models import (
    UploadedDataset, LabTrainingRun, LabModelResult, Job, Project, ProjectMember,
)
from app.api.routes.auth import get_current_user
from app.db.models import User

router = APIRouter(prefix="/projects/{project_id}/model-lab", tags=["model-lab"])

# ─── Storage directories ──────────────────────────────────────────────────────

def _dataset_dir(project_id: int) -> Path:
    p = UPLOAD_PATH / "datasets" / str(project_id)
    p.mkdir(parents=True, exist_ok=True)
    return p

def _artifact_dir(project_id: int) -> Path:
    p = UPLOAD_PATH / "model_artifacts" / str(project_id)
    p.mkdir(parents=True, exist_ok=True)
    return p

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_file(path: Path, original_name: str) -> dict:
    """Parse CSV or XLSX and return metadata + first 500 rows."""
    name_lower = original_name.lower()
    try:
        if name_lower.endswith(".csv"):
            df = pd.read_csv(path, dtype=str, nrows=2000, keep_default_na=False)
            sheet = None
        else:
            xf = pd.ExcelFile(path)
            sheet = xf.sheet_names[0]
            df = pd.read_excel(path, sheet_name=sheet, dtype=str, nrows=2000, keep_default_na=False)
    except Exception as exc:
        return {"error": str(exc)}

    headers = list(df.columns)
    col_types: dict[str, str] = {}
    for col in headers:
        vals = df[col].dropna().tolist()
        non_empty = [v for v in vals if v.strip() != ""]
        if not non_empty:
            col_types[col] = "text"
            continue
        bool_set = {"0", "1", "true", "false", "yes", "no"}
        if all(v.lower() in bool_set for v in non_empty):
            col_types[col] = "boolean"
            continue
        numeric_ok = sum(1 for v in non_empty if _is_numeric(v))
        if numeric_ok / len(non_empty) >= 0.80:
            col_types[col] = "numeric"
            continue
        uniq = len(set(non_empty))
        if uniq <= 20 and uniq <= len(non_empty) * 0.5:
            col_types[col] = "categorical"
            continue
        col_types[col] = "text"

    return {
        "headers": headers,
        "col_types": col_types,
        "row_count": len(df),
        "col_count": len(headers),
        "sheet": sheet,
        "error": None,
    }


def _is_numeric(v: str) -> bool:
    try:
        float(v)
        return True
    except ValueError:
        return False


def _dataset_to_dict(ds: UploadedDataset) -> dict:
    return {
        "id": ds.id,
        "project_id": ds.project_id,
        "original_name": ds.original_name,
        "dataset_family": ds.dataset_family,
        "row_count": ds.row_count,
        "col_count": ds.col_count,
        "headers": json.loads(ds.headers_json or "[]"),
        "column_types": json.loads(ds.column_types_json or "{}"),
        "column_mapping": json.loads(ds.column_mapping_json or "{}"),
        "parse_status": ds.parse_status,
        "parse_error": ds.parse_error,
        "file_hash": ds.file_hash,
        "sheet_name": ds.sheet_name,
        "uploaded_at": ds.uploaded_at.isoformat() if ds.uploaded_at else None,
        "updated_at": ds.updated_at.isoformat() if ds.updated_at else None,
    }


def _result_to_dict(r: LabModelResult) -> dict:
    return {
        "id": r.id,
        "training_run_id": r.training_run_id,
        "model_name": r.model_name,
        "model_family": r.model_family,
        "status": r.status,
        "skip_reason": r.skip_reason,
        "error_message": r.error_message,
        "metrics": json.loads(r.metrics_json or "{}"),
        "parameters": json.loads(r.parameters_json or "{}"),
        "feature_cols": json.loads(r.feature_cols_json or "[]"),
        "target_col": r.target_col,
        "mae": r.mae,
        "rmse": r.rmse,
        "r_squared": r.r_squared,
        "concordance_index": r.concordance_index,
        "has_artifact": bool(r.artifact_path),
        "is_active": r.is_active,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    }


def _run_to_dict(
    run: LabTrainingRun,
    results: list[LabModelResult] | None = None,
    dataset_name: str | None = None,
) -> dict:
    d = {
        "id": run.id,
        "project_id": run.project_id,
        "dataset_id": run.dataset_id,
        "dataset_name": dataset_name,
        "job_id": run.job_id,
        "dataset_family": run.dataset_family,
        "n_trajectories": run.n_trajectories,
        "n_fitted": run.n_fitted,
        "status": run.status,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }
    if results is not None:
        d["model_results"] = [_result_to_dict(r) for r in results]
    return d


# ─── Background training task ─────────────────────────────────────────────────

def _bg_train(training_run_id: int, dataset_id: int, project_id: int, job_id: int):
    """Runs in a background thread. Uses its own DB session."""
    db = SessionLocal()
    try:
        run = db.query(LabTrainingRun).filter(LabTrainingRun.id == training_run_id).first()
        job = db.query(Job).filter(Job.id == job_id).first()
        ds  = db.query(UploadedDataset).filter(UploadedDataset.id == dataset_id).first()

        if not run or not ds:
            return

        run.status = "running"
        if job:
            job.status   = "running"
            job.progress = 5
            job.current_step = "Loading dataset"
        db.commit()

        # Load dataset
        try:
            fpath = Path(ds.file_path)
            name  = ds.original_name.lower()
            if name.endswith(".csv"):
                df = pd.read_csv(fpath, dtype=str, keep_default_na=False)
            else:
                df = pd.read_excel(fpath, dtype=str, keep_default_na=False, sheet_name=0)
        except Exception as exc:
            _fail(db, run, job, f"Cannot load file: {exc}")
            return

        mapping = json.loads(run.column_mapping_json or "{}")
        df_records = df.to_dict("records")

        if job:
            job.progress     = 15
            job.current_step = "Fitting models"
            db.commit()

        if run.dataset_family == "kinetic":
            # Pre-create pending rows so the frontend can show live model status
            kinetic_names = ["baranyi", "gompertz", "weibull_inact", "geeraerd"]
            placeholder: dict[str, LabModelResult] = {}
            for mname in kinetic_names:
                mr = LabModelResult(
                    training_run_id = training_run_id,
                    project_id      = project_id,
                    model_name      = mname,
                    model_family    = "kinetic",
                    status          = "pending",
                    is_active       = True,
                )
                db.add(mr)
                placeholder[mname] = mr
            if job:
                job.progress     = 20
                job.current_step = "Fitting kinetic models"
            db.commit()

            from app.services.kinetic_trainer import run_kinetic_training
            result = run_kinetic_training(df_records, mapping)

            if "error" in result:
                for mr in placeholder.values():
                    mr.status        = "failed"
                    mr.error_message = result["error"]
                _fail(db, run, job, result["error"])
                return

            run.n_trajectories = result.get("n_trajectories", 0)
            run.n_fitted       = result.get("n_fitted", 0)

            if job:
                job.progress     = 80
                job.current_step = "Saving model results"
                db.commit()

            summary = result.get("summary", {})
            for model_name, s in summary.items():
                n_conv = s.get("n_converged", 0)
                mr = placeholder.get(model_name)
                if mr is None:
                    continue
                mr.status         = "completed" if n_conv > 0 else "failed"
                mr.error_message  = None if n_conv > 0 else "No trajectories converged"
                mr.metrics_json   = json.dumps({
                    "n_converged": n_conv,
                    "mean_mae":    s.get("mean_mae"),
                    "mean_rmse":   s.get("mean_rmse"),
                    "median_rmse": s.get("median_rmse"),
                    "mean_r2":     s.get("mean_r2"),
                })
                mr.results_json   = json.dumps({
                    "trajectories": [
                        {
                            "trajectory_id": t["trajectory_id"],
                            "n_obs": t["n_obs"],
                            "fit": t["models"].get(model_name, {}),
                        }
                        for t in result.get("trajectories", [])
                    ]
                })
                mr.mae            = s.get("mean_mae")
                mr.rmse           = s.get("mean_rmse")
                mr.r_squared      = s.get("mean_r2")
                mr.completed_at   = datetime.utcnow()
            db.commit()

        else:  # survival
            # Pre-create pending rows
            survival_names = ["weibull_aft", "xgboost_aft", "rsf", "bayesian_aft"]
            placeholder = {}
            for mname in survival_names:
                mr = LabModelResult(
                    training_run_id = training_run_id,
                    project_id      = project_id,
                    model_name      = mname,
                    model_family    = "survival",
                    status          = "pending",
                    is_active       = True,
                )
                db.add(mr)
                placeholder[mname] = mr
            if job:
                job.progress     = 20
                job.current_step = "Fitting survival models"
            db.commit()

            from app.services.survival_trainer import run_survival_training
            art_dir = _artifact_dir(project_id)
            result  = run_survival_training(df_records, mapping, art_dir)

            if "error" in result:
                for mr in placeholder.values():
                    mr.status        = "failed"
                    mr.error_message = result["error"]
                _fail(db, run, job, result["error"])
                return

            if job:
                job.progress     = 80
                job.current_step = "Saving model results"
                db.commit()

            models_result = result.get("models", {})
            for model_name, mres in models_result.items():
                status = mres.get("status", "failed")
                mr = placeholder.get(model_name)
                if mr is None:
                    continue
                mr.status             = status
                mr.skip_reason        = mres.get("reason") if status == "skipped" else None
                mr.error_message      = mres.get("reason") if status == "failed" else None
                mr.metrics_json       = json.dumps({
                    "concordance_index": mres.get("concordance_index"),
                    "n_train": mres.get("n_train"),
                    "n_test":  mres.get("n_test"),
                })
                mr.concordance_index  = mres.get("concordance_index")
                mr.artifact_path      = mres.get("artifact_path")
                mr.feature_cols_json  = json.dumps(result.get("feature_cols", []))
                mr.target_col         = result.get("time_col")
                mr.event_col          = result.get("event_col")
                mr.completed_at       = datetime.utcnow()
            db.commit()

        run.status       = "completed"
        run.completed_at = datetime.utcnow()
        if job:
            job.status       = "completed"
            job.progress     = 100
            job.current_step = "Done"
            job.completed_at = datetime.utcnow()
            job.result_json  = json.dumps({"training_run_id": training_run_id})
        db.commit()

    except Exception as exc:
        db.rollback()
        _fail(db, run if 'run' in dir() else None,
              job if 'job' in dir() else None, str(exc))
    finally:
        db.close()


def _fail(db, run, job, msg: str):
    if run:
        run.status        = "failed"
        run.error_message = msg
        run.completed_at  = datetime.utcnow()
    if job:
        job.status        = "failed"
        job.error_message = msg
        job.completed_at  = datetime.utcnow()
        job.progress      = 0
    try:
        db.commit()
    except Exception:
        db.rollback()


# ─── DATASET ENDPOINTS ────────────────────────────────────────────────────────

@router.post("/datasets/upload")
async def upload_dataset(
    project_id:    int,
    background:    BackgroundTasks,
    file:          UploadFile = File(...),
    dataset_family: str = Form("kinetic"),
    force_replace: bool = Form(False),
    db: Session = Depends(get_db),
    user: User  = Depends(get_current_user),
):
    """Upload a CSV or XLSX training dataset. Detects duplicates by SHA-256 hash."""
    _check_project(db, project_id, user)
    project = db.query(Project).filter(Project.id == project_id).first()

    allowed = {".csv", ".xlsx", ".xls"}
    ext = Path(file.filename or "").suffix.lower()
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed)}")

    # Save temp file
    ds_dir   = _dataset_dir(project_id)
    uuid_name = f"{uuid.uuid4().hex}{ext}"
    dest     = ds_dir / uuid_name
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_hash = _sha256(dest)

    # Duplicate check within this project (same family)
    existing = db.query(UploadedDataset).filter(
        UploadedDataset.project_id    == project_id,
        UploadedDataset.file_hash     == file_hash,
        UploadedDataset.dataset_family == dataset_family,
        UploadedDataset.is_active     == True,
    ).first()

    if existing and not force_replace:
        dest.unlink(missing_ok=True)
        return {
            "duplicate": True,
            "dataset": _dataset_to_dict(existing),
            "message": "A dataset with this exact content already exists for this project. "
                       "Pass force_replace=true to upload a new version anyway.",
        }

    # Soft-delete old active dataset of same family
    old = db.query(UploadedDataset).filter(
        UploadedDataset.project_id    == project_id,
        UploadedDataset.dataset_family == dataset_family,
        UploadedDataset.is_active     == True,
    ).first()
    if old:
        old.is_active = False

    # Parse
    meta = _parse_file(dest, file.filename or uuid_name)

    ds = UploadedDataset(
        project_id         = project_id,
        uploader_id        = user.id,
        original_name      = file.filename or uuid_name,
        filename           = uuid_name,
        file_path          = str(dest),
        file_hash          = file_hash,
        dataset_family     = dataset_family,
        sheet_name         = meta.get("sheet"),
        row_count          = meta.get("row_count", 0),
        col_count          = meta.get("col_count", 0),
        headers_json       = json.dumps(meta.get("headers", [])),
        column_types_json  = json.dumps(meta.get("col_types", {})),
        column_mapping_json = "{}",
        parse_status       = "error" if meta.get("error") else "ready",
        parse_error        = meta.get("error"),
        is_active          = True,
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return {"duplicate": False, "dataset": _dataset_to_dict(ds)}


@router.get("/datasets")
def list_datasets(
    project_id: int,
    db: Session = Depends(get_db),
    user: User  = Depends(get_current_user),
):
    """Return all active datasets for this project (one per family, latest)."""
    _check_project(db, project_id, user)
    datasets = db.query(UploadedDataset).filter(
        UploadedDataset.project_id == project_id,
        UploadedDataset.is_active  == True,
    ).order_by(UploadedDataset.uploaded_at.desc()).all()
    return [_dataset_to_dict(d) for d in datasets]


@router.get("/datasets/{dataset_id}")
def get_dataset(
    project_id: int, dataset_id: int,
    db: Session = Depends(get_db),
    user: User  = Depends(get_current_user),
):
    ds = _get_ds(db, project_id, dataset_id, user)
    return _dataset_to_dict(ds)


class MappingUpdate(BaseModel):
    column_mapping: dict[str, str]
    dataset_family: str | None = None


@router.patch("/datasets/{dataset_id}")
def update_mapping(
    project_id: int, dataset_id: int,
    body: MappingUpdate,
    db: Session = Depends(get_db),
    user: User  = Depends(get_current_user),
):
    """Save column mapping + optionally update dataset family."""
    ds = _get_ds(db, project_id, dataset_id, user)
    ds.column_mapping_json = json.dumps(body.column_mapping)
    if body.dataset_family:
        ds.dataset_family = body.dataset_family
    ds.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ds)
    return _dataset_to_dict(ds)


@router.delete("/datasets/{dataset_id}", status_code=204)
def delete_dataset(
    project_id: int, dataset_id: int,
    db: Session = Depends(get_db),
    user: User  = Depends(get_current_user),
):
    ds = _get_ds(db, project_id, dataset_id, user)
    ds.is_active = False
    db.commit()


@router.get("/datasets/{dataset_id}/download")
def download_dataset(
    project_id: int, dataset_id: int,
    db: Session = Depends(get_db),
    user: User  = Depends(get_current_user),
):
    ds = _get_ds(db, project_id, dataset_id, user)
    path = Path(ds.file_path)
    if not path.exists():
        raise HTTPException(404, "File not found on server")
    return FileResponse(
        path=str(path),
        filename=ds.original_name,
        media_type="application/octet-stream",
    )


# ─── TRAINING ENDPOINTS ───────────────────────────────────────────────────────

class TrainRequest(BaseModel):
    dataset_id: int
    column_mapping: dict[str, str]
    dataset_family: str
    threshold: float | None = None     # log10 threshold for kinetic t_failure


@router.post("/train")
def start_training(
    project_id:  int,
    body:        TrainRequest,
    background:  BackgroundTasks,
    db:          Session = Depends(get_db),
    user:        User    = Depends(get_current_user),
):
    _check_project(db, project_id, user)
    ds = _get_ds(db, project_id, body.dataset_id, user)

    if ds.parse_status != "ready":
        raise HTTPException(400, "Dataset is not ready (parse error). Re-upload the file.")

    # Block duplicate in-progress jobs
    running = db.query(LabTrainingRun).filter(
        LabTrainingRun.project_id  == project_id,
        LabTrainingRun.dataset_id  == body.dataset_id,
        LabTrainingRun.status.in_(["queued", "running"]),
    ).first()
    if running:
        raise HTTPException(409, "A training job is already running for this dataset. Wait for it to finish or cancel it first.")

    # Persist mapping
    ds.column_mapping_json = json.dumps(body.column_mapping)
    ds.dataset_family      = body.dataset_family

    # Create job record
    job = Job(
        project_id   = project_id,
        job_type     = "training",
        status       = "queued",
        progress     = 0,
        current_step = "Queued",
        created_by   = user.id,
    )
    db.add(job)
    db.flush()

    # Create training run
    run = LabTrainingRun(
        project_id          = project_id,
        dataset_id          = body.dataset_id,
        job_id              = job.id,
        dataset_family      = body.dataset_family,
        column_mapping_json = json.dumps(body.column_mapping),
        status              = "queued",
        created_by          = user.id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Launch background worker (persists even when user leaves tab)
    background.add_task(_bg_train, run.id, body.dataset_id, project_id, job.id)

    return {
        "training_run_id": run.id,
        "job_id": job.id,
        "status": "queued",
        "message": "Training started. Poll /model-lab/runs/{id} for progress.",
    }


@router.get("/runs")
def list_runs(
    project_id: int,
    db: Session = Depends(get_db),
    user: User  = Depends(get_current_user),
):
    _check_project(db, project_id, user)
    runs = db.query(LabTrainingRun).filter(
        LabTrainingRun.project_id == project_id,
    ).order_by(LabTrainingRun.created_at.desc()).limit(20).all()

    # Batch-fetch model results and dataset names
    run_ids = [r.id for r in runs]
    ds_ids  = list({r.dataset_id for r in runs if r.dataset_id})
    all_results = db.query(LabModelResult).filter(
        LabModelResult.training_run_id.in_(run_ids)
    ).all() if run_ids else []
    ds_map = {
        d.id: d.original_name
        for d in db.query(UploadedDataset).filter(UploadedDataset.id.in_(ds_ids)).all()
    } if ds_ids else {}
    results_by_run: dict[int, list] = {}
    for mr in all_results:
        results_by_run.setdefault(mr.training_run_id, []).append(mr)

    return [
        _run_to_dict(r, results_by_run.get(r.id, []), ds_map.get(r.dataset_id))
        for r in runs
    ]


@router.get("/runs/{run_id}")
def get_run(
    project_id: int, run_id: int,
    db: Session = Depends(get_db),
    user: User  = Depends(get_current_user),
):
    _check_project(db, project_id, user)
    run = db.query(LabTrainingRun).filter(
        LabTrainingRun.id         == run_id,
        LabTrainingRun.project_id == project_id,
    ).first()
    if not run:
        raise HTTPException(404, "Training run not found")

    job = db.query(Job).filter(Job.id == run.job_id).first() if run.job_id else None
    results = db.query(LabModelResult).filter(
        LabModelResult.training_run_id == run_id
    ).all()
    ds = db.query(UploadedDataset).filter(UploadedDataset.id == run.dataset_id).first()

    d = _run_to_dict(run, results, ds.original_name if ds else None)
    if job:
        d["job"] = {
            "status":       job.status,
            "progress":     job.progress,
            "current_step": job.current_step,
            "error_message": job.error_message,
        }
    return d


# ─── MODEL REGISTRY ENDPOINTS ────────────────────────────────────────────────

@router.get("/models")
def list_models(
    project_id: int,
    db: Session = Depends(get_db),
    user: User  = Depends(get_current_user),
):
    _check_project(db, project_id, user)
    results = db.query(LabModelResult).filter(
        LabModelResult.project_id == project_id,
        LabModelResult.is_active  == True,
    ).order_by(LabModelResult.training_run_id.desc(), LabModelResult.created_at.desc()).all()
    return [_result_to_dict(r) for r in results]


@router.get("/models/{model_id}")
def get_model(
    project_id: int, model_id: int,
    db: Session = Depends(get_db),
    user: User  = Depends(get_current_user),
):
    _check_project(db, project_id, user)
    r = db.query(LabModelResult).filter(
        LabModelResult.id         == model_id,
        LabModelResult.project_id == project_id,
    ).first()
    if not r:
        raise HTTPException(404, "Model result not found")
    d = _result_to_dict(r)
    # Include full trajectory results for kinetic models
    if r.model_family == "kinetic":
        d["results"] = json.loads(r.results_json or "{}")
    return d


@router.delete("/models/{model_id}", status_code=204)
def delete_model(
    project_id: int, model_id: int,
    db: Session = Depends(get_db),
    user: User  = Depends(get_current_user),
):
    _check_project(db, project_id, user)
    r = db.query(LabModelResult).filter(
        LabModelResult.id         == model_id,
        LabModelResult.project_id == project_id,
    ).first()
    if not r:
        raise HTTPException(404)
    r.is_active = False
    db.commit()


# ─── PREDICTION ENDPOINT ──────────────────────────────────────────────────────

class PredictRequest(BaseModel):
    model_id:             int
    input_features:       dict[str, Any]
    required_shelf_life:  float | None = None
    start_date:           str  | None = None     # ISO date string


@router.post("/predict")
def predict(
    project_id: int,
    body:       PredictRequest,
    db:         Session = Depends(get_db),
    user:       User    = Depends(get_current_user),
):
    _check_project(db, project_id, user)
    r = db.query(LabModelResult).filter(
        LabModelResult.id         == body.model_id,
        LabModelResult.project_id == project_id,
        LabModelResult.is_active  == True,
    ).first()
    if not r:
        raise HTTPException(404, "Model not found")
    if r.status != "completed":
        raise HTTPException(400, f"Model is not trained (status: {r.status})")

    if r.model_family == "kinetic":
        return {"error": "Direct kinetic prediction via form is not yet implemented. "
                         "View fitted curves in the Model Registry."}

    if not r.artifact_path:
        raise HTTPException(400, "No saved model artifact. Retrain the model.")

    from app.services.survival_trainer import predict_survival
    result = predict_survival(
        artifact_path        = r.artifact_path,
        model_name           = r.model_name,
        input_features       = body.input_features,
        required_shelf_life  = body.required_shelf_life,
    )

    # Add spoilage date if start_date provided
    if body.start_date and "predicted_shelf_life_days" in result and not result.get("error"):
        try:
            from datetime import date, timedelta
            start = date.fromisoformat(body.start_date)
            shelf = result["predicted_shelf_life_days"]
            result["expected_spoilage_date"] = (start + timedelta(days=shelf)).isoformat()
        except Exception:
            pass

    return result


# ─── Guard helpers ────────────────────────────────────────────────────────────

def _check_project(db: Session, project_id: int, user: User):
    """Raise 404 if the project doesn't exist or the user has no access to it."""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    if p.owner_id == user.id:
        return
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id    == user.id,
    ).first()
    if not member:
        raise HTTPException(404, "Project not found")


def _get_ds(db: Session, project_id: int, dataset_id: int, user: User) -> UploadedDataset:
    _check_project(db, project_id, user)
    ds = db.query(UploadedDataset).filter(
        UploadedDataset.id         == dataset_id,
        UploadedDataset.project_id == project_id,
        UploadedDataset.is_active  == True,
    ).first()
    if not ds:
        raise HTTPException(404, "Dataset not found")
    return ds
