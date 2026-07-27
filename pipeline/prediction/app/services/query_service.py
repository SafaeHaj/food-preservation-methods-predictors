"""Query service: read-side access over the repositories."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.models import Experiment, Indicator, Ingredient, Measurement
from app.database.repositories import (
    ExperimentRepository,
    IndicatorRepository,
    IngredientRepository,
    MeasurementRepository,
)


class QueryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_experiments(self) -> list[Experiment]:
        return ExperimentRepository(self.db).list()

    def list_ingredients(self) -> list[Ingredient]:
        return IngredientRepository(self.db).list()

    def list_indicators(self) -> list[Indicator]:
        return IndicatorRepository(self.db).list()

    def measurements_for(self, experiment_id: str) -> list[Measurement]:
        return MeasurementRepository(self.db).for_experiment(experiment_id)
