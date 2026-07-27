"""Repository for measurements."""

from __future__ import annotations

from sqlalchemy import select

from app.database.models.measurement import Measurement
from app.database.repositories.base import BaseRepository


class MeasurementRepository(BaseRepository[Measurement]):
    model = Measurement

    def for_experiment(self, experiment_id: str) -> list[Measurement]:
        stmt = (
            select(Measurement)
            .where(Measurement.experiment_id == experiment_id)
            .order_by(Measurement.indicator_id, Measurement.day)
        )
        return list(self.db.scalars(stmt).all())
