"""ETL service: extract via a connector, then load into the database."""

from __future__ import annotations

import math

import pandas as pd
from sqlalchemy.orm import Session

from app.database.models import (
    Experiment,
    ExperimentIngredient,
    Indicator,
    Ingredient,
    Measurement,
)
from app.extraction.services import ExtractionService


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame rows as plain dicts: numpy scalars to Python, NaN to None."""
    out: list[dict] = []
    for rec in df.to_dict("records"):
        clean: dict = {}
        for key, value in rec.items():
            if hasattr(value, "item"):  # numpy scalar -> python scalar
                value = value.item()
            if isinstance(value, float) and math.isnan(value):
                value = None
            clean[key] = value
        out.append(clean)
    return out


class ETLService:
    """Loads the mock (or any connector's) dataset into the database, idempotently."""

    def __init__(self, db: Session, extraction: ExtractionService | None = None) -> None:
        self.db = db
        self.extraction = extraction or ExtractionService()

    def load(self) -> dict[str, int]:
        data = self.extraction.extract()

        # Clear children before parents so foreign keys are never dangling.
        for model in (Measurement, ExperimentIngredient, Experiment, Ingredient, Indicator):
            self.db.query(model).delete()
        self.db.flush()

        # Insert parents before children.
        self.db.add_all(Experiment(**r) for r in _records(data.experiments))
        self.db.add_all(Ingredient(**r) for r in _records(data.ingredients))
        self.db.add_all(Indicator(**r) for r in _records(data.indicators))
        self.db.flush()
        self.db.add_all(
            ExperimentIngredient(**r) for r in _records(data.experiment_ingredients)
        )
        self.db.add_all(Measurement(**r) for r in _records(data.measurements))
        self.db.commit()

        return {
            "experiments": len(data.experiments),
            "ingredients": len(data.ingredients),
            "indicators": len(data.indicators),
            "experiment_ingredients": len(data.experiment_ingredients),
            "measurements": len(data.measurements),
        }
