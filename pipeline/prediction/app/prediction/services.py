"""Prediction service.

The survival feature/model code under `features/` and `models/` still targets the old
`t_failure`/`event` schema and is not yet wired to the measurements schema, so this service
is a thin stub. Porting the ML pipeline is a separate follow-up.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PredictionResult:
    available: bool
    detail: str


class PredictionService:
    """Placeholder until feature engineering is ported to the measurements schema."""

    _DETAIL = (
        "Prediction is not yet wired to the measurements schema. The survival engines "
        "under app.prediction.models still consume the old t_failure/event modelling table."
    )

    def predict(self, context: dict, formulation: dict) -> PredictionResult:
        return PredictionResult(available=False, detail=self._DETAIL)
