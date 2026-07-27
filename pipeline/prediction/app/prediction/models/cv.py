"""Study-grouped cross-validation, shared by every engine.

A fold never splits one study. Batches within a study are not independent -- shared meat
lot, shared lab, shared operator, shared unmeasured everything -- so a random row-level
split would put near-duplicates of the test rows into training and report a score that
says more about the split than the model.

This is the one CV utility in the module: engines do not roll their own.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from app.prediction.models.base import SurvivalModel


def grouped_folds(
    groups: np.ndarray, n_splits: int = 5, seed: int = 0
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Fold indices grouped by ``experiment_ID``.

    `n_splits` is silently reduced to the number of distinct studies when there are
    fewer studies than requested folds -- with 3 studies you cannot have 5 clean folds,
    and GroupKFold would rather raise than quietly leak.
    """
    groups = np.asarray(groups)
    n_groups = int(pd.unique(groups).size)
    if n_groups < 2:
        raise ValueError("grouped CV needs at least 2 distinct studies")
    n_splits = min(n_splits, n_groups)
    splitter = GroupKFold(n_splits=n_splits)
    return [
        (tr, te)
        for tr, te in splitter.split(np.zeros(len(groups)), groups=groups)
    ]


def assert_no_group_leakage(
    folds: list[tuple[np.ndarray, np.ndarray]], groups: np.ndarray
) -> None:
    """Fail loudly if any study appears in both sides of a fold."""
    groups = np.asarray(groups)
    for i, (tr, te) in enumerate(folds):
        overlap = set(groups[tr]) & set(groups[te])
        if overlap:
            raise AssertionError(f"fold {i} leaks study/studies {sorted(overlap)}")


def concordance(
    y_time: np.ndarray, y_event: np.ndarray, risk_scores: np.ndarray
) -> float:
    """Harrell's C-index.

    `risk_scores` must be *risk*: higher = fails sooner. Engines that predict a survival
    *time* must negate before calling.
    """
    from sksurv.metrics import concordance_index_censored

    event = np.asarray(y_event).astype(bool)
    if event.sum() == 0:
        return float("nan")
    return float(
        concordance_index_censored(event, np.asarray(y_time, float), np.asarray(risk_scores, float))[0]
    )


def grouped_cv_score(
    model_factory: Callable[[], SurvivalModel],
    X: pd.DataFrame,
    y_time: np.ndarray,
    y_event: np.ndarray,
    groups: np.ndarray,
    n_splits: int = 5,
    seed: int = 0,
) -> dict[str, float | list[float]]:
    """Fit `model_factory()` on each training fold and score C-index on the held-out study.

    Returns per-fold scores plus mean/std. A fold whose test side has no events yields
    NaN and is excluded from the mean rather than silently scoring 0.
    """
    folds = grouped_folds(groups, n_splits=n_splits, seed=seed)
    assert_no_group_leakage(folds, groups)

    y_time = np.asarray(y_time, float)
    y_event = np.asarray(y_event, int)
    scores: list[float] = []

    for tr, te in folds:
        model = model_factory()
        model.fit(X.iloc[tr], y_time[tr], y_event[tr], groups=np.asarray(groups)[tr])
        # predict_point, not predict: CV needs ranking, and an interval here would cost a
        # full bootstrap per fold for no benefit.
        point = model.predict_point(X.iloc[te])
        # Longer predicted shelf life = lower risk.
        scores.append(concordance(y_time[te], y_event[te], -point))

    valid = [s for s in scores if not np.isnan(s)]
    return {
        "fold_scores": scores,
        "mean_c_index": float(np.mean(valid)) if valid else float("nan"),
        "std_c_index": float(np.std(valid)) if valid else float("nan"),
        "n_folds": len(folds),
        "n_folds_scored": len(valid),
    }


def iter_fold_assignments(
    groups: np.ndarray, n_splits: int = 5, seed: int = 0
) -> np.ndarray:
    """Fold id per row.

    This is the form the R bridge needs: the full dataset plus one fold-assignment column,
    so the fold loop can run inside a single R call rather than one subprocess per fold.
    """
    folds = grouped_folds(groups, n_splits=n_splits, seed=seed)
    assignment = np.full(len(groups), -1, dtype=int)
    for k, (_, te) in enumerate(folds):
        assignment[te] = k
    return assignment
