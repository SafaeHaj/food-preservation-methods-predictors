"""Repository for the experiment-ingredient junction."""

from __future__ import annotations

from sqlalchemy import select

from app.database.models.experiment_ingredient import ExperimentIngredient
from app.database.repositories.base import BaseRepository


class ExperimentIngredientRepository(BaseRepository[ExperimentIngredient]):
    model = ExperimentIngredient

    def for_experiment(self, experiment_id: str) -> list[ExperimentIngredient]:
        stmt = select(ExperimentIngredient).where(
            ExperimentIngredient.experiment_id == experiment_id
        )
        return list(self.db.scalars(stmt).all())
