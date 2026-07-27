"""Flat-table survival adapter.

Model-lab uploads a *flat* survival table -- one row per experimental unit -- plus a
``{column: role}`` mapping whose roles come from the frontend's ``columnRoles.ts`` (``time``,
``event``, ``study_id``, and predictor roles). The engines under :mod:`app.prediction.models`
instead consume a numeric design ``X`` with ``y_time`` / ``y_event`` / ``groups``.

This module bridges the two: it turns records + mapping into that design, and it keeps a
fitted :class:`FlatPreprocessor` so a single prediction row can be transformed identically at
inference time. It deliberately does **not** use the schema-specific pillar/interaction feature
builder (that needs the 5-table longitudinal data, absent from a flat upload); the mapped
predictor columns are used directly, one-hot encoding categoricals and standardizing numerics.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Roles consumed from the frontend column mapping (see pipeline/frontend/src/data/columnRoles.ts)
ROLE_TIME = "time"
ROLE_EVENT = "event"
ROLE_STUDY = "study_id"
_IGNORE_ROLES = {"ignore", "unassigned"}

#: numeric-vs-categorical cutoff: a column is numeric when >= this share of non-null values parse
_NUMERIC_SHARE = 0.80


@dataclass
class FlatPreprocessor:
    """Reproduces the training design for a new row at prediction time.

    Numeric columns are mean/std standardized with the *training* statistics; categorical
    columns are one-hot expanded over the *training* category set. Unknown categories and
    missing columns collapse to all-zero dummies (via the final reindex), which is the safe
    behaviour for an unseen predictor value.
    """

    numeric_cols: list[str]
    numeric_mean: dict[str, float]
    numeric_std: dict[str, float]
    categorical_cols: list[str]
    categories: dict[str, list[str]]
    output_columns: list[str]

    def transform(self, records: list[dict] | dict | pd.DataFrame) -> pd.DataFrame:
        if isinstance(records, dict):
            records = [records]
        df = records.copy() if isinstance(records, pd.DataFrame) else pd.DataFrame(records)
        cols: dict[str, np.ndarray] = {}
        for c in self.numeric_cols:
            if c in df.columns:
                v = pd.to_numeric(df[c], errors="coerce")
            else:
                v = pd.Series([np.nan] * len(df), index=df.index)
            mean = self.numeric_mean[c]
            std = self.numeric_std[c] or 1.0
            cols[c] = ((v.fillna(mean) - mean) / std).to_numpy(dtype=float)
        for c in self.categorical_cols:
            s = df[c].astype(str) if c in df.columns else pd.Series([""] * len(df), index=df.index)
            for cat in self.categories[c]:
                cols[f"{c}={cat}"] = (s == cat).to_numpy(dtype=float)
        out = pd.DataFrame(cols, index=df.index) if cols else pd.DataFrame(index=df.index)
        return out.reindex(columns=self.output_columns, fill_value=0.0)


@dataclass
class FlatDesign:
    X: pd.DataFrame            # standardized numeric + one-hot, engine-ready
    y_time: np.ndarray
    y_event: np.ndarray
    groups: np.ndarray
    time_col: str
    event_col: str
    study_col: str | None
    feature_cols: list[str]    # original mapped predictor columns (pre-encoding)
    preprocessor: FlatPreprocessor

    @property
    def n_rows(self) -> int:
        return len(self.y_time)


def _role_to_col(mapping: dict[str, str], columns: pd.Index) -> dict[str, str]:
    """Invert the ``{column: role}`` mapping to ``{role: column}`` for the singleton roles."""
    out: dict[str, str] = {}
    for col, role in mapping.items():
        if role is None or role in _IGNORE_ROLES or col not in columns:
            continue
        out.setdefault(role, col)
    return out


def build_flat_design(records: list[dict], mapping: dict[str, str]) -> FlatDesign:
    """Build the engine-ready design from flat records + a column mapping.

    Raises ``ValueError`` with a user-facing message when the mapping is unusable (no time /
    event / predictor columns) -- the caller turns that into a training ``{"error": ...}``.
    """
    df = pd.DataFrame(records)
    if df.empty:
        raise ValueError("No rows in the uploaded dataset.")

    roles = _role_to_col(mapping, df.columns)
    time_col = roles.get(ROLE_TIME)
    event_col = roles.get(ROLE_EVENT)
    study_col = roles.get(ROLE_STUDY)
    if not time_col:
        raise ValueError("No 'time' role mapped to a valid column.")
    if not event_col:
        raise ValueError("No 'event' role mapped to a valid column.")

    reserved = {time_col, event_col, study_col}
    feature_cols = [
        c for c in df.columns
        if c not in reserved and mapping.get(c) not in _IGNORE_ROLES and mapping.get(c) is not None
    ]
    if not feature_cols:
        raise ValueError("No feature columns mapped. Map at least one predictor.")

    # Labels: coerce, drop rows with unusable time/event, keep strictly-positive times.
    df = df.copy()
    df[time_col] = pd.to_numeric(df[time_col], errors="coerce")
    df[event_col] = pd.to_numeric(df[event_col], errors="coerce")
    df = df.dropna(subset=[time_col, event_col])
    df = df[df[time_col] > 0].reset_index(drop=True)
    if df.empty:
        raise ValueError("No rows with a positive time and a valid event indicator.")

    y_time = df[time_col].to_numpy(dtype=float)
    y_event = df[event_col].astype(int).to_numpy()

    # Split predictors into numeric vs categorical (same 80% rule the frontend uses).
    numeric_cols: list[str] = []
    categorical_cols: list[str] = []
    for c in feature_cols:
        conv = pd.to_numeric(df[c], errors="coerce")
        nonnull = df[c].notna().sum()
        if nonnull and conv.notna().sum() / nonnull >= _NUMERIC_SHARE:
            numeric_cols.append(c)
        else:
            categorical_cols.append(c)

    # Numeric: median-impute, standardize, drop constant columns (unidentifiable).
    numeric_mean: dict[str, float] = {}
    numeric_std: dict[str, float] = {}
    numeric_frames: dict[str, np.ndarray] = {}
    for c in numeric_cols:
        v = pd.to_numeric(df[c], errors="coerce")
        median = float(v.median()) if v.notna().any() else 0.0
        v = v.fillna(median)
        std = float(v.std(ddof=0))
        if std <= 1e-12:
            continue  # constant column carries no signal and breaks standardization
        mean = float(v.mean())
        numeric_mean[c] = mean
        numeric_std[c] = std
        numeric_frames[c] = ((v - mean) / std).to_numpy(dtype=float)
    kept_numeric = list(numeric_frames)

    # Categorical: one-hot over the training category set.
    categories: dict[str, list[str]] = {}
    onehot: dict[str, np.ndarray] = {}
    for c in categorical_cols:
        s = df[c].astype(str)
        cats = sorted(s.dropna().unique().tolist())
        categories[c] = cats
        for cat in cats:
            onehot[f"{c}={cat}"] = (s == cat).to_numpy(dtype=float)

    output_columns = kept_numeric + list(onehot)
    if not output_columns:
        raise ValueError("All mapped predictors were constant or empty; nothing to fit.")

    X = pd.DataFrame({**numeric_frames, **onehot})[output_columns]

    if study_col is not None and df[study_col].notna().any():
        groups = df[study_col].astype(str).to_numpy()
    else:
        # No study grouping supplied: each row is its own group. Grouped CV then degrades to
        # row-level CV, and the Weibull frailty stage correctly reports "fewer than 2 studies".
        groups = np.array([f"row{i}" for i in range(len(df))], dtype=object)

    preprocessor = FlatPreprocessor(
        numeric_cols=kept_numeric,
        numeric_mean=numeric_mean,
        numeric_std=numeric_std,
        categorical_cols=categorical_cols,
        categories=categories,
        output_columns=output_columns,
    )
    return FlatDesign(
        X=X,
        y_time=y_time,
        y_event=y_event,
        groups=groups,
        time_col=time_col,
        event_col=event_col,
        study_col=study_col,
        feature_cols=feature_cols,
        preprocessor=preprocessor,
    )
