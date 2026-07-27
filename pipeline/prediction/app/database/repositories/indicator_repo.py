"""Repository for indicators."""

from __future__ import annotations

from app.database.models.indicator import Indicator
from app.database.repositories.base import BaseRepository


class IndicatorRepository(BaseRepository[Indicator]):
    model = Indicator
