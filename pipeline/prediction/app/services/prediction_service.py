"""Prediction service: business-facing wrapper over the prediction engine (stubbed)."""

from __future__ import annotations

from app.prediction.services import PredictionResult
from app.prediction.services import PredictionService as _Engine


class PredictionService:
    def __init__(self) -> None:
        self._engine = _Engine()

    def predict(self, context: dict, formulation: dict) -> PredictionResult:
        return self._engine.predict(context, formulation)
