"""Shared machinery for the shelf-life benchmarks.

Everything the notebook needs to turn ``survival.csv`` / ``hazard.csv`` into
model matrices, split them by study, and score a model the same way each time.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score, brier_score_loss, f1_score, mean_absolute_error, r2_score, roc_auc_score,
)

DATA_DIR = Path(__file__).parent / "data"
SEED = 42
SPLIT_SHARES = {"train": 0.6, "validation": 0.2, "test": 0.2}
SPLIT_NAMES = list(SPLIT_SHARES)

CATEGORICAL_FEATURES = [
    "meat_matrix", "packaging_atmosphere", "treatment_type", "ingredient_name",
    "functional_class", "ingredient_source", "indicator_name", "indicator_type",
    "indicator_unit",
]
# Knowable before the storage trial starts: formulation, matrix, protocol,
# the indicator being tracked and its day-0 reading.
FORMULATION_FEATURES = [
    "is_control", "n_ingredients", "total_dose_ppm", "log_dose", "logp_wmean", "mw_wmean",
]
PROTOCOL_FEATURES = [
    "storage_temperature_c", "matrix_moisture_percent", "matrix_protein_percent",
    "matrix_fat_percent", "matrix_ph", "matrix_water_activity",
]
INDICATOR_FEATURES = [
    "indicator_threshold", "initial_value", "initial_fraction_of_threshold",
    "threshold_headroom",
]
# Trial-design variables. These describe the storage study that is being run,
# not its outcome: how long the product is meant to be kept and how often it is
# sampled are chosen before day 0. The failure day is reported on that grid, so
# a model that does not see the grid cannot place the answer on it.
DESIGN_FEATURES = ["planned_window_days", "n_sampling_points", "sampling_interval_days"]

NUMERIC_FEATURES = (
    FORMULATION_FEATURES + PROTOCOL_FEATURES + INDICATOR_FEATURES + DESIGN_FEATURES
)
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
# The person-period table adds the query day; the survival table does not have one.
HAZARD_FEATURES = ["day"] + FEATURES


def load(name: str) -> pd.DataFrame:
    return enrich(pd.read_csv(DATA_DIR / name))


def enrich(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["threshold_headroom"] = frame["indicator_threshold"] - frame["initial_value"]
    frame["log_dose"] = np.log1p(frame["total_dose_ppm"].clip(lower=0))
    frame["planned_window_days"] = frame["censor_day"]
    frame["n_sampling_points"] = frame["n_points"]
    frame["sampling_interval_days"] = (
        frame["censor_day"] / frame["n_points"].replace(0, np.nan)
    )
    return frame


_LEVELS: dict[str, list[str]] = {}


def category_levels() -> dict[str, list[str]]:
    """Category levels pooled over both model tables.

    Deriving them per split would give each part its own level set, and a model
    that encodes categories natively then refuses a level it did not see while
    training. Fixing them once keeps every matrix comparable.
    """
    if not _LEVELS:
        frames = [pd.read_csv(DATA_DIR / name) for name in ("survival.csv", "hazard.csv")]
        for column in CATEGORICAL_FEATURES:
            values = pd.concat(
                [frame[column] for frame in frames if column in frame], ignore_index=True
            )
            _LEVELS[column] = sorted(values.dropna().astype(str).unique())
    return _LEVELS


def encode(frame: pd.DataFrame, features: list[str] | None = None) -> pd.DataFrame:
    """Model matrix with stable category dtypes, so every split shares them."""
    features = features or FEATURES
    matrix = frame.reindex(columns=features).copy()
    levels = category_levels()
    for column in matrix.columns.intersection(CATEGORICAL_FEATURES):
        values = matrix[column].astype("object").where(matrix[column].notna(), other=None)
        matrix[column] = pd.Categorical(values, categories=levels[column])
    return matrix


def split_studies(frame: pd.DataFrame, label: str, seed: int = SEED) -> dict[str, set]:
    """Assign whole studies to train / validation / test.

    Studies are walked in order of their outcome rate and dropped into whichever
    part is furthest below its row quota, so the three parts end up comparable in
    both size and base rate. Splitting on studies rather than rows keeps arms
    from one paper out of two different parts.
    """
    profile = (
        frame.groupby("study_id")
        .agg(rows=(label, "size"), rate=(label, "mean"))
        .sample(frac=1.0, random_state=seed)
        .sort_values("rate")
    )
    quota = {name: share * profile["rows"].sum() for name, share in SPLIT_SHARES.items()}
    assigned: dict[str, list] = {name: [] for name in SPLIT_SHARES}
    filled = dict.fromkeys(SPLIT_SHARES, 0.0)
    for study, row in profile.iterrows():
        name = min(filled, key=lambda part: filled[part] / quota[part])
        assigned[name].append(study)
        filled[name] += row["rows"]
    return {name: set(studies) for name, studies in assigned.items()}


def split_masks(frame: pd.DataFrame, parts: dict[str, set]) -> dict[str, np.ndarray]:
    return {name: frame["study_id"].isin(studies).to_numpy() for name, studies in parts.items()}


def classification_scores(truth: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    prediction = probability > 0.5
    return {
        "Accuracy": accuracy_score(truth, prediction),
        "ROC_AUC": roc_auc_score(truth, probability),
        "F1": f1_score(truth, prediction),
        "Brier": brier_score_loss(truth, probability),
    }


def regression_scores(truth: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    return {
        "R2": r2_score(truth, prediction),
        "MAE": mean_absolute_error(truth, prediction),
        "RMSE": float(np.sqrt(np.mean((truth - prediction) ** 2))),
    }


def summarise(rows: list[dict], metrics: list[str]) -> pd.DataFrame:
    table = pd.DataFrame(rows)
    ordered = ["model", "split"] + [m for m in metrics if m in table.columns]
    return table[ordered].round(3)


def split_report(frame: pd.DataFrame, masks: dict[str, np.ndarray], label: str) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "split": name,
            "studies": frame.loc[mask, "study_id"].nunique(),
            "rows": int(mask.sum()),
            "positive_rate": round(float(frame.loc[mask, label].mean()), 3),
        }
        for name, mask in masks.items()
    ])
