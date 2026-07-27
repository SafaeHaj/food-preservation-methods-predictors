"""Model-lab routes -- bind HTTP to the dataset, training and prediction services."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from shared.db.database import get_db
from shared.db.models import Project, User

from app.api.deps import get_current_user, require_project, require_project_contributor
from app.schemas.model_lab import (
    DatasetOut, DatasetUploadOut, MappingUpdate, ModelResultOut, PredictRequest,
    PredictionOut, TrainingAccepted, TrainingRunOut, TrainRequest,
)
from app.services import dataset_service, model_prediction_service, training_service

router = APIRouter(prefix="/projects/{project_id}/model-lab", tags=["model-lab"])


# ─── Datasets ─────────────────────────────────────────────────────────────────

@router.post("/datasets/upload", response_model=DatasetUploadOut)
def upload_dataset(
    file: UploadFile = File(...),
    dataset_family: str = Form("kinetic"),
    force_replace: bool = Form(False),
    project: Project = Depends(require_project_contributor),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return dataset_service.upload(
        db, project.id, user.id,
        filename=file.filename or "dataset",
        stream=file.file,
        family=dataset_family,
        force_replace=force_replace,
    )


@router.get("/datasets", response_model=list[DatasetOut])
def list_datasets(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return dataset_service.list_datasets(db, project.id)


@router.get("/datasets/{dataset_id}", response_model=DatasetOut)
def get_dataset(
    dataset_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return dataset_service.get_dataset(db, project.id, dataset_id)


@router.patch("/datasets/{dataset_id}", response_model=DatasetOut)
def update_mapping(
    dataset_id: int,
    body: MappingUpdate,
    project: Project = Depends(require_project_contributor),
    db: Session = Depends(get_db),
):
    return dataset_service.update_mapping(db, project.id, dataset_id, body)


@router.delete("/datasets/{dataset_id}", status_code=204)
def delete_dataset(
    dataset_id: int,
    project: Project = Depends(require_project_contributor),
    db: Session = Depends(get_db),
):
    dataset_service.deactivate(db, project.id, dataset_id)


@router.get("/datasets/{dataset_id}/download")
def download_dataset(
    dataset_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    path, filename = dataset_service.file_for_download(db, project.id, dataset_id)
    return FileResponse(str(path), filename=filename, media_type="application/octet-stream")


# ─── Training ─────────────────────────────────────────────────────────────────

@router.post("/train", status_code=202, response_model=TrainingAccepted)
def start_training(
    body: TrainRequest,
    project: Project = Depends(require_project_contributor),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return training_service.start_training(db, project.id, user.id, body)


@router.get("/runs", response_model=list[TrainingRunOut])
def list_runs(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return training_service.list_runs(db, project.id)


@router.get("/runs/{run_id}", response_model=TrainingRunOut)
def get_run(
    run_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return training_service.get_run(db, project.id, run_id)


# ─── Model registry and prediction ────────────────────────────────────────────

@router.get("/models", response_model=list[ModelResultOut])
def list_models(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return model_prediction_service.list_models(db, project.id)


@router.get("/models/{model_id}", response_model=ModelResultOut)
def get_model(
    model_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return model_prediction_service.get_model(db, project.id, model_id)


@router.delete("/models/{model_id}", status_code=204)
def delete_model(
    model_id: int,
    project: Project = Depends(require_project_contributor),
    db: Session = Depends(get_db),
):
    model_prediction_service.deactivate_model(db, project.id, model_id)


@router.post("/predict", response_model=PredictionOut)
def predict(
    body: PredictRequest,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return model_prediction_service.predict(db, project.id, body)
