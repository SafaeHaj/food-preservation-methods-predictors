"""Shared derived-column formulas used by data_processing.ipynb, data_filling.ipynb,
and baranyi_growth_modelling.ipynb.

Keeping this in one place avoids formula drift between notebooks that all need to
recompute the same three derived columns after generating or reconstructing
`post_threshold_(day)` / `post_threshold_count` values.
"""

from __future__ import annotations

import pandas as pd


def compute_inhibition_features(df: pd.DataFrame) -> pd.DataFrame:
    """Recompute the three derived inhibition/proximity columns from source columns.

    Mirrors data_processing.ipynb's `compute_inhibition_features` exactly.
    """
    new_cols = {
        "initial_inhibition_factor": (
            (df["pre_threshold_count"] - df["initial_count_(day_0)"])
            / df["pre_threshold_(day)"].replace(0, pd.NA)
        ),
        "post_inhibition_factor": (
            (df["post_threshold_count"] - df["pre_threshold_count"])
            / (df["post_threshold_(day)"] - df["pre_threshold_(day)"]).clip(lower=1e-6)
        ),
        "post_threshold_proximity_index_2(tpi)": (
            df["post_threshold_count"] / df["lower_level_threshold_(log_cfu/g)"].replace(0, pd.NA)
        ),
    }
    return df.assign(**new_cols)
