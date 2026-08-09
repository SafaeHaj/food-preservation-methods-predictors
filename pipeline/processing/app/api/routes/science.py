"""Routes over the scientific schema — experiments, ingredients, indicators, measurements.

Read-only except for one field: an indicator's threshold. Everything else here is
extraction output and is corrected by re-extracting, not by editing rows.

There is deliberately no trigger endpoint. Extraction is started through the workspace
(`POST .../workspace` then `POST .../send-to-llm`), which is the same pipeline this data
comes from; the previous `POST /food-extract/{paper_id}` ran a second, separately-written
copy of it.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from shared.db.database import get_db
from shared.db.models import Project, User

from app.api.deps import (
    get_current_user, require_project, require_project_contributor,
)
from app.schemas.science import (
    EvidenceOut, ExperimentDetailOut, ExperimentSummaryOut, IndicatorOut, IndicatorUpdate,
    IngredientOut, MeasurementOut,
)
from app.services import science_service

router = APIRouter(tags=["science"])


@router.get("/projects/{project_id}/experiments", response_model=list[ExperimentSummaryOut])
def list_experiments(
    paper_id: Optional[int] = Query(None),
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return science_service.list_experiments(db, project.id, paper_id)


@router.get(
    "/projects/{project_id}/experiments/{experiment_id}",
    response_model=ExperimentDetailOut,
)
def get_experiment(
    experiment_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return science_service.get_experiment(db, project.id, experiment_id)


@router.get(
    "/projects/{project_id}/experiments/{experiment_id}/measurements",
    response_model=list[MeasurementOut],
)
def list_measurements(
    experiment_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return science_service.list_measurements(db, project.id, experiment_id)


@router.get("/projects/{project_id}/ingredients", response_model=list[IngredientOut])
def list_ingredients(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return science_service.list_ingredients(db, project.id)


@router.get("/projects/{project_id}/indicators", response_model=list[IndicatorOut])
def list_indicators(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return science_service.list_indicators(db, project.id)


@router.patch(
    "/projects/{project_id}/indicators/{indicator_id}",
    response_model=IndicatorOut,
)
def update_indicator(
    indicator_id: int,
    body: IndicatorUpdate,
    project: Project = Depends(require_project_contributor),
    db: Session = Depends(get_db),
):
    """Set or clear an indicator's threshold — the one editable field in the schema."""
    return science_service.update_indicator(db, project.id, indicator_id, body)


@router.get("/evidence/{evidence_id}", response_model=EvidenceOut)
def get_evidence(
    evidence_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return science_service.get_evidence(db, evidence_id, user)
