"""Seeded synthetic connector for end-to-end testing before real data is wired in.

Emits a small, deterministic, internally consistent dataset across all five tables so the
store and concordance checks can be exercised end to end. 
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from app.database import columns as C
from app.extraction.connectors.base import ExperimentConnector

_UNIT = "% (w/w)"
_DAYS = (0, 3, 6, 9)
_MATRICES = ("beef", "chicken", "fish")

# ingredient_id -> (ingredient_name, functional_class, source)
_INGREDIENTS: dict[str, tuple[str, str, str]] = {
    "ING01": ("rosemary_extract", "phenol", "plant"),
    "ING02": ("thymol", "essential_oil", "plant"),
    "ING03": ("nisin", "protein", "microbial"),
    "ING04": ("lactic_acid", "organic_acid", "microbial"),
    "ING05": ("sodium_chloride", "mineral", "synthetic"),
    "ING06": ("chitosan", "carbohydrate", "animal"),
    "ING07": ("green_tea_extract", "phenol", "plant"),
    "ING08": ("inulin", "fiber", "plant"),
}

# treatment name -> formulation (ingredient_id -> concentration). Empty is an untreated control.
_TREATMENTS: dict[str, dict[str, float]] = {
    "control": {},
    "essential_oil": {"ING02": 1.0},
    "organic_acid": {"ING04": 1.5},
    "phenol_blend": {"ING01": 0.5, "ING07": 0.5},
    "protein": {"ING03": 0.2},
}

# indicator_id -> (indicator_type, indicator_unit, indicator_threshold). pH has no threshold.
_INDICATORS: dict[str, tuple[str, str, float]] = {
    "TVC": ("TVC", "log CFU/g", 7.0),
    "TVBN": ("TVBN", "mg/100g", 25.0),
    "PH": ("pH", "pH", np.nan),
    "TBARS": ("TBARS", "mg MDA/kg", 2.0),
}

# indicator_id -> (day-0 baseline, per-day slope). Spoilage indicators rise over storage.
_TRAJECTORY: dict[str, tuple[float, float]] = {
    "TVC": (3.0, 0.55),
    "TVBN": (10.0, 2.0),
    "PH": (5.8, 0.02),
    "TBARS": (0.3, 0.18),
}


class MockConnector(ExperimentConnector):
    """Generates a small deterministic dataset across the five tables.

    Parameters
    ----------
    seed:
        Makes the light measurement jitter reproducible.
    """

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed
        self._experiments: pd.DataFrame | None = None
        self._bridge: pd.DataFrame | None = None
        self._measurements: pd.DataFrame | None = None

    # -- ExperimentConnector -----------------------------------------------------------

    def get_experiments(self) -> pd.DataFrame:
        self._ensure_generated()
        assert self._experiments is not None
        return self._experiments.copy()

    def get_ingredients(self) -> pd.DataFrame:
        rows = [
            {
                C.INGREDIENT_ID: iid,
                C.INGREDIENT_NAME: name,
                C.FUNCTIONAL_CLASS: klass,
                C.SOURCE: source,
            }
            for iid, (name, klass, source) in _INGREDIENTS.items()
        ]
        return pd.DataFrame(rows, columns=C.INGREDIENT_COLUMNS)

    def get_indicators(self) -> pd.DataFrame:
        rows = [
            {
                C.INDICATOR_ID: iid,
                C.INDICATOR_TYPE: itype,
                C.INDICATOR_UNIT: unit,
                C.INDICATOR_THRESHOLD: threshold,
            }
            for iid, (itype, unit, threshold) in _INDICATORS.items()
        ]
        return pd.DataFrame(rows, columns=C.INDICATOR_COLUMNS)

    def get_experiment_ingredients(
        self, experiment_ids: Sequence[str] | None = None
    ) -> pd.DataFrame:
        self._ensure_generated()
        assert self._bridge is not None
        out = self._bridge
        if experiment_ids is not None:
            out = out[out[C.EXPERIMENT_ID].isin(list(experiment_ids))]
        return out.copy().reset_index(drop=True)

    def get_measurements(
        self, experiment_ids: Sequence[str] | None = None
    ) -> pd.DataFrame:
        self._ensure_generated()
        assert self._measurements is not None
        out = self._measurements
        if experiment_ids is not None:
            out = out[out[C.EXPERIMENT_ID].isin(list(experiment_ids))]
        return out.copy().reset_index(drop=True)

    # -- generation --------------------------------------------------------------------

    def _ensure_generated(self) -> None:
        if self._experiments is not None:
            return
        rng = np.random.default_rng(self.seed)

        experiment_rows: list[dict] = []
        bridge_rows: list[dict] = []
        measurement_rows: list[dict] = []

        idx = 0
        for matrix in _MATRICES:
            for treatment, formulation in _TREATMENTS.items():
                idx += 1
                experiment_id = f"EXP{idx:03d}"
                experiment_rows.append(
                    {
                        C.EXPERIMENT_ID: experiment_id,
                        C.MEAT_MATRIX: matrix,
                        C.TREATMENT: treatment,
                    }
                )
                for ingredient_id, conc in formulation.items():
                    bridge_rows.append(
                        {
                            C.EXPERIMENT_ID: experiment_id,
                            C.INGREDIENT_ID: ingredient_id,
                            C.CONCENTRATION: conc,
                            C.CONCENTRATION_UNIT: _UNIT,
                        }
                    )

                # Treated experiments spoil more slowly than the untreated control.
                protection = 1.0 if not formulation else 0.7
                for indicator_id, (base, slope) in _TRAJECTORY.items():
                    for day in _DAYS:
                        jitter = float(rng.normal(0.0, 0.03))
                        value = base + slope * day * protection + jitter
                        measurement_rows.append(
                            {
                                C.EXPERIMENT_ID: experiment_id,
                                C.DAY: day,
                                C.INDICATOR_ID: indicator_id,
                                C.INDICATOR_VALUE: round(value, 3),
                            }
                        )

        self._experiments = pd.DataFrame(experiment_rows, columns=C.EXPERIMENT_COLUMNS)
        self._bridge = pd.DataFrame(bridge_rows, columns=C.EXPERIMENT_INGREDIENT_COLUMNS)
        self._measurements = pd.DataFrame(measurement_rows, columns=C.MEASUREMENT_COLUMNS)
