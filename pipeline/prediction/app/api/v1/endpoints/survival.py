"""Survival train/predict endpoints for the model-lab flat-table path.

These replace the colleague's in-process ``survival_trainer``. The processing/model-lab layer
calls them over internal HTTP; request/response shapes match what its ``_bg_train`` and
``/predict`` code already consume, so the frontend contract is unchanged.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.survival_service import SurvivalPredictionService, SurvivalTrainingService

router = APIRouter(prefix="/survival", tags=["survival"])


class TrainRequest(BaseModel):
    records: list[dict[str, Any]] = Field(..., description="Flat dataset rows (one unit per row).")
    mapping: dict[str, str] = Field(..., description="{column: role} from the frontend column mapping.")


class PredictRequest(BaseModel):
    model_ref: str = Field(..., description="Opaque artifact handle returned by /train.")
    model_name: str
    input_features: dict[str, Any] = Field(default_factory=dict)
    required_shelf_life: float | None = None


@router.post("/train")
def train(request: TrainRequest) -> dict[str, Any]:
    return SurvivalTrainingService().train(request.records, request.mapping)


@router.post("/predict")
def predict(request: PredictRequest) -> dict[str, Any]:
    return SurvivalPredictionService().predict(
        request.model_ref, request.model_name, request.input_features, request.required_shelf_life
    )
