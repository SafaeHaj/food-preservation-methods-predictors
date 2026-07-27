"""Turn a scenario Design into a standardized model matrix + survival targets.

Schema-generic: any column that never varies across the input is dropped (it cannot be
identified), and the rest are standardized so a group penalty compares blocks on equal
footing. `groups` is the schema's ``treatment`` column -- the effective independent unit, so
replicates of one formulation never split across CV folds. When ``treatment`` is unique per
experiment this degrades to per-experiment grouping, which is the correct fallback.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.prediction.scenarios import Design


@dataclass
class ModelData:
    scenario: str
    X: pd.DataFrame                 # standardized, indexed by experiment_id
    X_raw: pd.DataFrame             # same columns, original units
    y_time: np.ndarray
    y_event: np.ndarray
    groups: np.ndarray              # treatment per row
    experiment_ids: np.ndarray
    feature_scales: pd.Series       # per-column std used to standardize (original units)
    feature_means: pd.Series
    dropped_constant: list[str] = field(default_factory=list)
    #: one group per column -> the Weibull group penalty degenerates to per-column Lasso,
    #: which is correct here: with meat_matrix/treatment constant there are no interaction
    #: blocks to keep together.
    feature_groups: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=int))
    group_names: list[str] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.y_time)

    @property
    def n_groups(self) -> int:
        return int(pd.unique(self.groups).size)


def build_model_data(design: Design) -> ModelData:
    raw = design.frame.set_index("experiment_id")[design.feature_cols].astype(float)

    scale_all = raw.std(ddof=0)
    constant = scale_all[scale_all <= 1e-12].index.tolist()
    kept = [c for c in design.feature_cols if c not in constant]
    raw = raw[kept]

    mean = raw.mean()
    scale = raw.std(ddof=0).where(lambda s: s > 1e-12, 1.0)
    X = (raw - mean) / scale

    meta = design.frame.set_index("experiment_id")
    return ModelData(
        scenario=design.name,
        X=X,
        X_raw=raw,
        y_time=meta["time"].to_numpy(dtype=float),
        y_event=meta["event"].to_numpy(dtype=int),
        groups=meta["treatment"].to_numpy(),
        experiment_ids=np.asarray(raw.index),
        feature_scales=scale,
        feature_means=mean,
        dropped_constant=constant,
        feature_groups=np.arange(len(kept)),
        group_names=list(kept),
    )
