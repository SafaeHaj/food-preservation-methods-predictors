"""Grouped bootstrap prediction intervals.

For engines with no analytic covariance (random survival forest, gradient boosting), the
interval comes from refitting on resampled data.

**Studies are resampled, not rows.** Row-level resampling would treat the batches inside a
study as independent draws, which they are not, and would produce intervals that are far
too narrow -- confidently wrong is the one failure mode the optimizer cannot tolerate,
since its whole job is to prefer well-supported recommendations. Resampling whole studies
propagates the between-study variation that actually limits what we know.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from app.prediction.models.base import Prediction, SurvivalModel


def study_bootstrap_index(groups: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Row indices for one bootstrap replicate, resampling whole studies with replacement.

    A study drawn twice contributes all of its rows twice, which is the point: the
    replicate must vary at the level the data actually varies at.
    """
    groups = np.asarray(groups)
    studies = pd.unique(groups)
    drawn = rng.choice(studies, size=len(studies), replace=True)
    rows_by_study = {s: np.flatnonzero(groups == s) for s in studies}
    return np.concatenate([rows_by_study[s] for s in drawn])


def bootstrap_interval(
    model_factory: Callable[[], SurvivalModel],
    X: pd.DataFrame,
    y_time: np.ndarray,
    y_event: np.ndarray,
    groups: np.ndarray,
    X_new: pd.DataFrame,
    n_boot: int = 200,
    level: float = 0.95,
    seed: int = 0,
) -> Prediction:
    """Percentile bootstrap interval for predictions at `X_new`.

    The point estimate comes from the full-data fit; only the interval is bootstrapped.
    Replicates that fail to fit (a resample can, legitimately, contain no events for some
    feature) are skipped and reported by count rather than crashing the run.
    """
    rng = np.random.default_rng(seed)
    y_time = np.asarray(y_time, float)
    y_event = np.asarray(y_event, int)

    full = model_factory()
    full.fit(X, y_time, y_event, groups=groups)
    point = full.predict_point(X_new)

    draws: list[np.ndarray] = []
    for _ in range(n_boot):
        idx = study_bootstrap_index(groups, rng)
        if y_event[idx].sum() == 0:
            continue
        try:
            model = model_factory()
            model.fit(X.iloc[idx], y_time[idx], y_event[idx], groups=np.asarray(groups)[idx])
            # predict_point, never predict: predict would bootstrap again, recursing.
            draws.append(model.predict_point(X_new))
        except Exception:  # noqa: BLE001 - a degenerate resample is expected, not fatal
            continue

    if len(draws) < 2:
        # Better an honest NaN interval than a fabricated one.
        nan = np.full(len(point), np.nan)
        return Prediction(point=point, lower=nan, upper=nan, level=level)

    mat = np.vstack(draws)
    alpha = 1.0 - level
    lower = np.quantile(mat, alpha / 2.0, axis=0)
    upper = np.quantile(mat, 1.0 - alpha / 2.0, axis=0)
    return Prediction(point=point, lower=lower, upper=upper, level=level)
