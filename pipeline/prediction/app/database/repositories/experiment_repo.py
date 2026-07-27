"""Repository for experiments."""

from __future__ import annotations

from app.database.models.experiment import Experiment
from app.database.repositories.base import BaseRepository


class ExperimentRepository(BaseRepository[Experiment]):
    model = Experiment
