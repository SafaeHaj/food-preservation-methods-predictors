"""Evaluation: survival-native ranking + operational horizon classification.

The engines predict a shelf-life *time*, not a class, so "accuracy / recall / F1" only exist
against an operational question: **is this batch spoiled by day h?** That target is derived
from the labels (`spoiled_by_h = event == 1 AND time <= h`) and scored against each model's
**cross-validated** predicted time (`predicted_spoiled = t_hat <= h`), so the classification
numbers are out-of-sample, not memorized.

Horizons are chosen from the data, not fixed: only cutpoints that split the cohort into both
classes are kept (a horizon before the first failure or after the last is degenerate and
carries no information). Survival ranking is Harrell's C-index under study-grouped CV. The
"confidence" the engines expose is a 95% interval on the predicted time; its mean width is
reported as a calibration-free uncertainty summary.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from app.prediction.models.base import SurvivalModel
from app.prediction.models.cv import grouped_cv_score, grouped_folds

EngineFactory = Callable[[], SurvivalModel]


@dataclass
class EngineResult:
    name: str
    scenario: str
    ok: bool
    reason: str = ""                      # populated when ok is False
    c_index_mean: float = float("nan")
    c_index_std: float = float("nan")
    n_folds_scored: int = 0
    ibs: float | None = None
    ci_level: float = 0.95
    ci_width_mean: float = float("nan")
    point_mean: float = float("nan")
    n_selected: int | None = None      # features surviving selection (Weibull group-Lasso); None if N/A
    horizons: dict[int, dict[str, float]] = field(default_factory=dict)
    primary_horizon: int | None = None
    oof: pd.DataFrame | None = None       # experiment_id, time, event, oof_pred, fold
    feature_effects: pd.DataFrame | None = None


def choose_horizons(y_time: np.ndarray, y_event: np.ndarray) -> tuple[list[int], int | None]:
    """Non-degenerate 'spoiled by day h' cutpoints, plus a primary (nearest the median).

    A horizon is kept only if `0 < #spoiled_by_h < n`, i.e. both classes are present.
    """
    t = np.asarray(y_time, float)
    e = np.asarray(y_event, int)
    n = len(t)
    cand = sorted({int(x) for x in np.unique(t[e == 1])})
    horizons = [h for h in cand if 0 < int(((e == 1) & (t <= h)).sum()) < n]
    if not horizons:
        return [], None
    med = float(np.median(t[e == 1])) if e.any() else float(np.median(t))
    primary = min(horizons, key=lambda h: abs(h - med))
    return horizons, primary


def oof_predicted_times(
    factory: EngineFactory,
    X: pd.DataFrame,
    y_time: np.ndarray,
    y_event: np.ndarray,
    groups: np.ndarray,
    n_splits: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Out-of-fold predicted times (study-grouped folds), aligned to X's rows."""
    folds = grouped_folds(groups, n_splits=n_splits, seed=seed)
    oof = np.full(len(X), np.nan)
    fold_id = np.full(len(X), -1, dtype=int)
    yt = np.asarray(y_time, float)
    ye = np.asarray(y_event, int)
    for k, (tr, te) in enumerate(folds):
        model = factory()
        model.fit(X.iloc[tr], yt[tr], ye[tr], groups=np.asarray(groups)[tr])
        oof[te] = model.predict_point(X.iloc[te])
        fold_id[te] = k
    return oof, fold_id


def classification_at(
    y_time: np.ndarray, y_event: np.ndarray, pred_time: np.ndarray, h: int
) -> dict[str, float]:
    """Confusion-matrix metrics for 'spoiled by day h' from predicted times."""
    t = np.asarray(y_time, float)
    e = np.asarray(y_event, int)
    valid = ~np.isnan(pred_time)
    y_true = ((e == 1) & (t <= h))[valid].astype(int)
    y_pred = (np.asarray(pred_time, float)[valid] <= h).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "horizon_day": float(h),
        "n": int(valid.sum()),
        "n_positive": int(y_true.sum()),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn),
    }


def _rsf_ibs(model: SurvivalModel, X: pd.DataFrame, y_time: np.ndarray, y_event: np.ndarray) -> float | None:
    """In-sample integrated Brier score for an RSF (needs a survival function). Guarded."""
    try:
        from sksurv.metrics import integrated_brier_score

        under = getattr(model, "model_", None)
        cols = getattr(model, "columns_", list(X.columns))
        if under is None:
            return None
        Xf = X.reindex(columns=cols, fill_value=0.0)
        t = np.asarray(y_time, float)
        e = np.asarray(y_event, bool)
        lo, hi = float(t.min()), float(t.max())
        if hi - lo < 1e-6:
            return None
        times = np.linspace(lo + 0.05 * (hi - lo), hi - 0.05 * (hi - lo), 5)
        surv_fns = under.predict_survival_function(Xf)
        estimate = np.asarray([[fn(tt) for tt in times] for fn in surv_fns])
        y_struct = np.array(list(zip(e, t, strict=True)), dtype=[("event", "?"), ("time", "<f8")])
        return float(integrated_brier_score(y_struct, y_struct, estimate, times))
    except Exception:
        return None


def evaluate_engine(
    name: str,
    factory: EngineFactory,
    X: pd.DataFrame,
    y_time: np.ndarray,
    y_event: np.ndarray,
    groups: np.ndarray,
    experiment_ids: np.ndarray,
    scenario: str,
    n_splits: int,
    seed: int,
    feature_scales: pd.Series | None = None,
) -> EngineResult:
    """Fit + score one engine on one scenario, catching dependency/fit failures per engine."""
    res = EngineResult(name=name, scenario=scenario, ok=False)
    try:
        # 1. study-grouped C-index
        cv = grouped_cv_score(factory, X, y_time, y_event, np.asarray(groups),
                              n_splits=n_splits, seed=seed)
        res.c_index_mean = float(cv["mean_c_index"])
        res.c_index_std = float(cv["std_c_index"])
        res.n_folds_scored = int(cv["n_folds_scored"])

        # 2. out-of-fold predicted times -> horizon classification
        oof, fold_id = oof_predicted_times(factory, X, y_time, y_event, np.asarray(groups),
                                           n_splits, seed)
        horizons, primary = choose_horizons(y_time, y_event)
        res.horizons = {h: classification_at(y_time, y_event, oof, h) for h in horizons}
        res.primary_horizon = primary
        res.oof = pd.DataFrame({
            "experiment_id": experiment_ids,
            "time": np.asarray(y_time, float),
            "event": np.asarray(y_event, int),
            "oof_pred": oof,
            "fold": fold_id,
        })

        # 3. full-data fit: interval width ("confidence") + effects + IBS
        model = factory().fit(X, y_time, y_event, groups=np.asarray(groups))
        selected = getattr(model, "selected_columns_", None)
        res.n_selected = len(selected) if selected is not None else None
        pred = model.predict(X)
        res.ci_level = float(getattr(pred, "level", 0.95))
        res.ci_width_mean = float(np.nanmean(pred.width))
        res.point_mean = float(np.nanmean(pred.point))
        if name == "rsf":
            res.ibs = _rsf_ibs(model, X, y_time, y_event)
        try:
            eff = (model.feature_effects(scales=feature_scales)
                   if name == "weibull_aft" else model.feature_effects())
        except TypeError:
            eff = model.feature_effects()
        res.feature_effects = eff
        res.ok = True
    except Exception as exc:  # per-engine isolation: one broken engine never sinks the run
        res.reason = f"{type(exc).__name__}: {exc}"
    return res
