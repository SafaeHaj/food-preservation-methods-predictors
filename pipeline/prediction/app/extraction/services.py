"""Extraction service: pull the five canonical frames from a connector and validate them."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.core.config import Config, get_config
from app.database.checks import raise_on_violation, run_concordance_checks
from app.extraction.connectors.base import ExperimentConnector
from app.extraction.connectors.mock import MockConnector


@dataclass(frozen=True)
class ExtractedData:
    experiments: pd.DataFrame
    ingredients: pd.DataFrame
    indicators: pd.DataFrame
    experiment_ingredients: pd.DataFrame
    measurements: pd.DataFrame


class ExtractionService:
    """Reads a connector's output and runs concordance checks before it is loaded."""

    def __init__(
        self,
        connector: ExperimentConnector | None = None,
        config: Config | None = None,
    ) -> None:
        self.connector = connector or MockConnector()
        self.config = config or get_config()

    def extract(self, validate: bool = True) -> ExtractedData:
        data = ExtractedData(
            experiments=self.connector.get_experiments(),
            ingredients=self.connector.get_ingredients(),
            indicators=self.connector.get_indicators(),
            experiment_ingredients=self.connector.get_experiment_ingredients(),
            measurements=self.connector.get_measurements(),
        )
        if validate:
            violations = run_concordance_checks(
                data.experiments,
                data.ingredients,
                data.experiment_ingredients,
                data.indicators,
                data.measurements,
                self.config,
            )
            raise_on_violation(violations)
        return data
