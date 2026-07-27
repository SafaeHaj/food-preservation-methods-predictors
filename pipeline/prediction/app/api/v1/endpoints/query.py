"""Query endpoints: read experiments, ingredients, indicators, and measurements."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.database.schemas import (
    ExperimentRead,
    IndicatorRead,
    IngredientRead,
    MeasurementRead,
)
from app.services import QueryService

router = APIRouter(prefix="/query", tags=["query"])


@router.get("/experiments", response_model=list[ExperimentRead])
def list_experiments(db: Session = Depends(get_db)):
    return QueryService(db).list_experiments()


@router.get("/ingredients", response_model=list[IngredientRead])
def list_ingredients(db: Session = Depends(get_db)):
    return QueryService(db).list_ingredients()


@router.get("/indicators", response_model=list[IndicatorRead])
def list_indicators(db: Session = Depends(get_db)):
    return QueryService(db).list_indicators()


@router.get(
    "/experiments/{experiment_id}/measurements",
    response_model=list[MeasurementRead],
)
def experiment_measurements(experiment_id: str, db: Session = Depends(get_db)):
    return QueryService(db).measurements_for(experiment_id)
