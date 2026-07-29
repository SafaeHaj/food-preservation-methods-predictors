"""Prediction routes — shelf-life models trained on the built dataset.

    GET /projects/{pid}/prediction    what this project could train, and whether it can yet

The surface is deliberately thin. Training and inference belong to the prediction service,
which owns the survival engines (Weibull-AFT / RSF / GBS / R-frailty) and the fitted
artifacts; this service's job is to hand it a dataset and to hold the project-scoped
authorization it has no way to perform itself. `services/survival_trainer` is that seam and
is already written.

What is missing is the step before it: `services/dataset_builder` does not yet produce the
flat records the engines take, so there is nothing to train on and no `POST .../train` here
to pretend otherwise. Adding it is a two-line route once the builder lands.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from shared.config import get_processing_settings
from shared.db.database import get_db
from shared.db.models import Project

from app.api.deps import require_project
from app.schemas.dataset import DatasetSource
from app.services import dataset_builder

router = APIRouter(tags=["prediction"])


class PredictionStatus(BaseModel):
    """Whether this project is in a position to train anything, and on what."""

    project_id: int
    #: False until the dataset builder is written. The screen says so rather than offering
    #: a button that would fail.
    available: bool = False
    reason: str
    #: Engine names the prediction service exposes, for the screen to name what is coming.
    engines: list[str] = Field(default_factory=list)
    source: DatasetSource


@router.get("/projects/{project_id}/prediction", response_model=PredictionStatus)
def get_prediction_status(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    source = dataset_builder.source_counts(db, project.id)

    if source.experiments == 0:
        reason = "No experiments have been extracted for this project yet."
    elif source.indicators_with_threshold == 0:
        reason = (
            "No indicator has a threshold. Shelf life is the day an indicator crosses its "
            "limit, so at least one threshold must be set in the scientific database "
            "before anything can be labelled."
        )
    else:
        reason = "The dataset builder is not implemented yet, so there is nothing to train on."

    return PredictionStatus(
        project_id=project.id,
        available=False,
        reason=reason,
        engines=list(get_processing_settings().SURVIVAL_ENGINES),
        source=source,
    )
