"""Gradient-boosted survival engine (XGBoost AFT).

Uses XGBoost's native `survival:aft` objective, which takes censoring through interval
bounds: a right-censored batch is `[t, +inf)` -- it failed *somewhere* after t, we just
stopped looking. That is the correct encoding, and it is why this is preferable to
regressing on observed times and discarding censored rows, which would bias every estimate
downward by throwing away exactly the longest-lived batches.

On study structure: gradient boosting has no frailty term either. Same explicit treatment
as the RSF -- grouped CV, study-level bootstrap intervals, and `experiment_ID` as an
opt-in feature. See `models.rsf` for why that flag defaults off.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.core.config import Config
from app.prediction.models.base import Prediction, SurvivalModel
from app.prediction.models.bootstrap import bootstrap_interval


class GradientBoostedSurvivalEngine(SurvivalModel):
    """XGBoost AFT behind the common interface.

    `predict` on an AFT booster returns a predicted survival *time* directly, so it is
    already on the same scale as the Weibull engine's median -- no inversion needed.
    """

    name = "gbs"

    def __init__(self, config: Config) -> None:
        self.config = config
        self.model_: Any = None
        self.columns_: list[str] = []
        self._train: tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray] | None = None

    def fit(
        self,
        X: pd.DataFrame,
        y_time: np.ndarray,
        y_event: np.ndarray,
        groups: np.ndarray | None = None,
        **kwargs: Any,
    ) -> "GradientBoostedSurvivalEngine":
        import xgboost as xgb

        t, e = self._validate_fit_inputs(X, y_time, y_event)
        Xf = self._augment(X, groups)
        self.columns_ = list(Xf.columns)

        dtrain = xgb.DMatrix(Xf.to_numpy(dtype=float), feature_names=self.columns_)
        # Right censoring: observed -> [t, t]; censored -> [t, inf).
        dtrain.set_float_info("label_lower_bound", t)
        dtrain.set_float_info("label_upper_bound", np.where(e == 1, t, np.inf))

        p = self.config.model.tree_engines.gbs
        params = {
            "objective": "survival:aft",
            "eval_metric": "aft-nloglik",
            "aft_loss_distribution": p.get("aft_loss_distribution", "normal"),
            "aft_loss_distribution_scale": float(p.get("aft_loss_distribution_scale", 1.0)),
            "tree_method": "hist",
            "max_depth": int(p.get("max_depth", 3)),
            "eta": float(p.get("learning_rate", 0.05)),
            "seed": int(p.get("seed", 0)),
            "verbosity": 0,
        }
        self.model_ = xgb.train(params, dtrain, num_boost_round=int(p.get("n_rounds", 200)))
        self._train = (X, t, e, np.asarray(groups) if groups is not None else np.arange(len(t)))
        return self

    def _augment(self, X: pd.DataFrame, groups: np.ndarray | None) -> pd.DataFrame:
        if not self.config.model.tree_engines.include_experiment_id_as_feature:
            return X
        if groups is None:
            return X
        out = X.copy()
        out["experiment_ID_code"] = pd.Categorical(
            np.asarray(groups).astype(str)
        ).codes.astype(float)
        return out

    def predict_point(self, X: pd.DataFrame) -> np.ndarray:
        import xgboost as xgb

        if self.model_ is None:
            raise RuntimeError("call fit() before predict_point()")
        Xf = X.reindex(columns=self.columns_, fill_value=0.0)
        d = xgb.DMatrix(Xf.to_numpy(dtype=float), feature_names=self.columns_)
        return np.asarray(self.model_.predict(d), dtype=float)

    def predict(self, X: pd.DataFrame) -> Prediction:
        """Point estimate plus a study-level bootstrap interval."""
        if self.model_ is None:
            raise RuntimeError("call fit() before predict()")
        unc = self.config.model.uncertainty
        if self._train is None:  # pragma: no cover - fit() always sets it
            point = self.predict_point(X)
            nan = np.full(len(X), np.nan)
            return Prediction(point=point, lower=nan, upper=nan, level=unc.level)

        Xtr, t, e, groups = self._train
        return bootstrap_interval(
            model_factory=lambda: GradientBoostedSurvivalEngine(self.config),
            X=Xtr, y_time=t, y_event=e, groups=groups, X_new=X,
            n_boot=unc.n_boot, level=unc.level, seed=self.config.model.cv.seed,
        )

    def feature_effects(self) -> pd.DataFrame | None:
        """Gain-based importances -- a ranking, with no direction and no units."""
        if self.model_ is None:
            raise RuntimeError("call fit() before feature_effects()")
        gain = self.model_.get_score(importance_type="gain")
        if not gain:
            return None
        return pd.DataFrame(
            {"feature": list(gain), "importance": [float(v) for v in gain.values()]}
        ).sort_values("importance", ascending=False, ignore_index=True)
