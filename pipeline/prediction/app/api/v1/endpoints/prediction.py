"""Prediction endpoint (stubbed until the ML pipeline is ported to the new schema)."""

from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.services import PredictionService

router = APIRouter(prefix="/prediction", tags=["prediction"])


class PredictionRequest(BaseModel):
    context: dict[str, str] = Field(default_factory=dict)
    formulation: dict[str, float] = Field(default_factory=dict)


@router.post("")
def predict(request: PredictionRequest) -> JSONResponse:
    result = PredictionService().predict(request.context, request.formulation)
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"available": result.available, "detail": result.detail},
    )
