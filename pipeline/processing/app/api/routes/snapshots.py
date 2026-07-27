"""Dataset snapshots + export runs."""

import hashlib
import json
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from shared.auth import get_current_user
from shared.db.database import get_db
from shared.errors import BusinessRuleError, NotFoundError
from shared.db.models import DatasetSnapshot, ExportRun, User
from shared.schemas.canonical import ExportRequest, ExportRunOut, SnapshotCreate, SnapshotOut

from app.services import scoping

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.get("", response_model=list[SnapshotOut])
def list_snapshots(
    project_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = scoping.scope_query(
        db, db.query(DatasetSnapshot), DatasetSnapshot.project_id, project_id, current_user,
    )
    return q.order_by(DatasetSnapshot.created_at.desc()).offset(skip).limit(limit).all()


@router.post("", response_model=SnapshotOut, status_code=status.HTTP_201_CREATED)
def create_snapshot(
    payload: SnapshotCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filters_json = json.dumps(payload.filters, sort_keys=True)
    feature_json = json.dumps(payload.feature_config, sort_keys=True)
    snap_hash = hashlib.sha256(
        f"{payload.project_id}:{filters_json}:{feature_json}:{payload.includes_imputed}:{payload.only_approved}"
        .encode()
    ).hexdigest()

    snap = DatasetSnapshot(
        project_id=payload.project_id,
        label=payload.label,
        description=payload.description,
        filters_json=filters_json,
        feature_config_json=feature_json,
        includes_imputed=payload.includes_imputed,
        only_approved=payload.only_approved,
        snapshot_hash=snap_hash,
        created_by=current_user.id,
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


@router.get("/{snapshot_id}", response_model=SnapshotOut)
def get_snapshot(
    snapshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    snap = db.query(DatasetSnapshot).filter(DatasetSnapshot.id == snapshot_id).first()
    if not snap:
        raise NotFoundError("Snapshot not found")
    return snap


@router.post("/export", response_model=ExportRunOut, status_code=status.HTTP_202_ACCEPTED)
def create_export(
    payload: ExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = ExportRun(
        project_id=payload.project_id,
        snapshot_id=payload.snapshot_id,
        format=payload.format,
        status="pending",
        filters_json=json.dumps(payload.filters),
        created_by=current_user.id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    from app.tasks import run_export
    run_export.delay(run.id)
    return run


@router.get("/exports/{run_id}", response_model=ExportRunOut)
def get_export_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = db.query(ExportRun).filter(ExportRun.id == run_id).first()
    if not run:
        raise NotFoundError("Export run not found")
    return run


@router.get("/exports/{run_id}/download")
def download_export(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from fastapi.responses import FileResponse
    import os

    run = db.query(ExportRun).filter(ExportRun.id == run_id).first()
    if not run:
        raise NotFoundError("Export run not found")
    if run.status != "completed":
        raise BusinessRuleError(f"Export not ready (status: {run.status})")
    if not run.file_path or not os.path.exists(run.file_path):
        raise NotFoundError("Export file not found on disk")

    media_types = {
        "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv_zip": "application/zip",
        "json": "application/json",
        "parquet": "application/octet-stream",
    }
    return FileResponse(
        run.file_path,
        media_type=media_types.get(run.format, "application/octet-stream"),
        filename=os.path.basename(run.file_path),
    )
