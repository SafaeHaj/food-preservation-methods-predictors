from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

import pandas as pd


class ExperimentConnector(ABC):
    """Abstract source of the normalized 5-table dataset."""

    @abstractmethod
    def get_experiments(self) -> pd.DataFrame:
        """One row per experiment.

        Columns :data:`app.database.columns.EXPERIMENT_COLUMNS`:
        ``experiment_id`` (primary key), ``meat_matrix``, ``treatment``.
        """

    @abstractmethod
    def get_ingredients(self) -> pd.DataFrame:
        """The ingredient lookup, one row per unique ingredient.

        Columns :data:`app.database.columns.INGREDIENT_COLUMNS`:
        ``ingredient_id`` (primary key), ``ingredient_name`` (unique),
        ``functional_class``, ``source``.
        """

    @abstractmethod
    def get_indicators(self) -> pd.DataFrame:
        """The indicator lookup, one row per measurable indicator.

        Columns :data:`app.database.columns.INDICATOR_COLUMNS`:
        ``indicator_id`` (primary key), ``indicator_type``, ``indicator_unit``,
        ``indicator_threshold`` (nullable).
        """

    @abstractmethod
    def get_experiment_ingredients(
        self, experiment_ids: Sequence[str] | None = None
    ) -> pd.DataFrame:
        """The experiment-ingredient junction for the given experiments (all if None).

        Columns :data:`app.database.columns.EXPERIMENT_INGREDIENT_COLUMNS`:
        ``experiment_id``, ``ingredient_id``, ``concentration``, ``concentration_unit``.
        An untreated control simply has no rows here.
        """

    @abstractmethod
    def get_measurements(
        self, experiment_ids: Sequence[str] | None = None
    ) -> pd.DataFrame:
        """Longitudinal observations for the given experiments (all if None).

        Columns :data:`app.database.columns.MEASUREMENT_COLUMNS`:
        ``experiment_id``, ``day``, ``indicator_id``, ``indicator_value``, keyed by
        ``(experiment_id, day, indicator_id)``.
        """
