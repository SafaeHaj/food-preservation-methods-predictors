"""Read routes over the structured extraction output (`ext_*`).

There is deliberately no trigger endpoint here. Extraction is started through the workspace
(`POST .../workspace` then `POST .../send-to-llm`), which is the same pipeline this data
comes from; the previous `POST /food-extract/{paper_id}` ran a second, separately-written
copy of it.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from shared.db.database import get_db
from shared.db.models import Project, User

from app.api.deps import get_current_user, require_project, verify_signed_asset
from app.schemas.ext_data import (
    EvidenceOut, ExperimentDetailOut, ExperimentSummaryOut, IndicatorOut, IngredientOut,
    MeasurementOut,
)
from app.services import ext_data_service

router = APIRouter(tags=["extracted-data"])


@router.get("/projects/{project_id}/food-experiments", response_model=list[ExperimentSummaryOut])
def list_experiments(
    paper_id: Optional[int] = Query(None),
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return ext_data_service.list_experiments(db, project.id, paper_id)


@router.get(
    "/projects/{project_id}/food-experiments/{experiment_id}",
    response_model=ExperimentDetailOut,
)
def get_experiment(
    experiment_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return ext_data_service.get_experiment(db, project.id, experiment_id)


@router.get(
    "/projects/{project_id}/food-experiments/{experiment_id}/measurements",
    response_model=list[MeasurementOut],
)
def list_measurements(
    experiment_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return ext_data_service.list_measurements(db, project.id, experiment_id)


@router.get("/projects/{project_id}/ingredients", response_model=list[IngredientOut])
def list_ingredients(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return ext_data_service.list_ingredients(db, project.id)


@router.get("/projects/{project_id}/indicators", response_model=list[IndicatorOut])
def list_indicators(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return ext_data_service.list_indicators(db, project.id)


@router.get("/evidence/{evidence_id}", response_model=EvidenceOut)
def get_evidence(
    evidence_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ext_data_service.get_evidence(db, evidence_id, user)


@router.get("/evidence/{evidence_id}/image", dependencies=[Depends(verify_signed_asset)])
def get_evidence_image(evidence_id: int, db: Session = Depends(get_db)):
    path = ext_data_service.get_evidence_file(db, evidence_id, thumbnail=False)
    return FileResponse(str(path), media_type="image/png")


@router.get("/evidence/{evidence_id}/thumbnail", dependencies=[Depends(verify_signed_asset)])
def get_evidence_thumbnail(evidence_id: int, db: Session = Depends(get_db)):
    path = ext_data_service.get_evidence_file(db, evidence_id, thumbnail=True)
    return FileResponse(str(path), media_type="image/png")
