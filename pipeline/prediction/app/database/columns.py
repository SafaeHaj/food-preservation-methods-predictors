"""Canonical column vocabulary for the normalized 5-table schema."""

from __future__ import annotations

from typing import Final

# --- experiments ----------------------------------------------------------------------
EXPERIMENT_ID: Final = "experiment_id"
MEAT_MATRIX: Final = "meat_matrix"
TREATMENT: Final = "treatment"

# --- ingredients ----------------------------------------------------------------------
INGREDIENT_ID: Final = "ingredient_id"
INGREDIENT_NAME: Final = "ingredient_name"
FUNCTIONAL_CLASS: Final = "functional_class"
SOURCE: Final = "source"

# --- experiment_ingredients -----------------------------------------------------------
CONCENTRATION: Final = "concentration"
CONCENTRATION_UNIT: Final = "concentration_unit"

# --- indicators -----------------------------------------------------------------------
INDICATOR_ID: Final = "indicator_id"
INDICATOR_TYPE: Final = "indicator_type"
INDICATOR_UNIT: Final = "indicator_unit"
INDICATOR_THRESHOLD: Final = "indicator_threshold"

# --- measurements ---------------------------------------------------------------------
DAY: Final = "day"
INDICATOR_VALUE: Final = "indicator_value"

EXPERIMENT_COLUMNS: Final = [EXPERIMENT_ID, MEAT_MATRIX, TREATMENT]
INGREDIENT_COLUMNS: Final = [INGREDIENT_ID, INGREDIENT_NAME, FUNCTIONAL_CLASS, SOURCE]
EXPERIMENT_INGREDIENT_COLUMNS: Final = [
    EXPERIMENT_ID,
    INGREDIENT_ID,
    CONCENTRATION,
    CONCENTRATION_UNIT,
]
INDICATOR_COLUMNS: Final = [
    INDICATOR_ID,
    INDICATOR_TYPE,
    INDICATOR_UNIT,
    INDICATOR_THRESHOLD,
]
MEASUREMENT_COLUMNS: Final = [EXPERIMENT_ID, DAY, INDICATOR_ID, INDICATOR_VALUE]
