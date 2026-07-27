"""Random Survival Forest engine.

On study structure: an RSF has no frailty term. Rather than pretend otherwise, the
clustering is honoured two ways, both explicit:

* **Grouped CV** -- scoring always splits by `experiment_ID` (see `models.cv`).
* **Grouped bootstrap** -- prediction intervals resample whole studies, so the interval
  reflects between-study variation rather than within-study pseudo-replication.
* Optionally, `experiment_ID` can be added as a feature via
  `model.tree_engines.include_experiment_id_as_feature`. It is **off** by default: the
  optimizer asks about formulations for a *new*, unseen batch, and a model that leans on
  study identity has learned something it cannot use at prediction time. Turning it on is
  a legitimate choice for in-sample interpretation; it is a config flag, not a silent one.

`predict` returns a survival **time** so that it is comparable with the AFT engine. sksurv
predicts a risk score, so the model's own survival function is inverted for the median
instead of returning the risk directly.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.core.config import Config
from app.prediction.models.base import Prediction, SurvivalModel
from app.prediction.models.bootstrap import bootstrap_interval


def to_structured(y_time: np.ndarray, y_event: np.ndarray) -> np.ndarray:
    """sksurv's (event: bool, time: float) record array."""
    return np.array(
        list(zip(np.asarray(y_event).astype(bool), np.asarray(y_time, float), strict=True)),
        dtype=[("event", "?"), ("time", "<f8")],
    )


def median_from_survival(
    times: np.ndarray, surv_probs: np.ndarray
) -> float:
    """First time at which the survival function drops to 0.5.

    When a curve never reaches 0.5 within the observed horizon (a long-lived formulation
    under administrative censoring) the largest available time is returned. That is a
    lower bound, not the true median, and it is the honest answer -- the data does not
    contain the median.
    """
    below = np.flatnonzero(surv_probs <= 0.5)
    return float(times[below[0]]) if below.size else float(times[-1])


class RandomSurvivalForestEngine(SurvivalModel):
    """sksurv RandomSurvivalForest behind the common interface."""

    name = "rsf"

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
    ) -> "RandomSurvivalForestEngine":
        from sksurv.ensemble import RandomSurvivalForest

        t, e = self._validate_fit_inputs(X, y_time, y_event)
        Xf = self._augment(X, groups)
        self.columns_ = list(Xf.columns)

        params = self.config.model.tree_engines.rsf
        self.model_ = RandomSurvivalForest(
            n_estimators=int(params.get("n_estimators", 200)),
            min_samples_leaf=int(params.get("min_samples_leaf", 3)),
            random_state=int(params.get("seed", 0)),
            n_jobs=1,
        ).fit(Xf, to_structured(t, e))
        self._train = (X, t, e, np.asarray(groups) if groups is not None else np.arange(len(t)))
        return self

    def _augment(self, X: pd.DataFrame, groups: np.ndarray | None) -> pd.DataFrame:
        if not self.config.model.tree_engines.include_experiment_id_as_feature:
            return X
        if groups is None:
            return X
        out = X.copy()
        codes = pd.Categorical(np.asarray(groups).astype(str)).codes
        out["experiment_ID_code"] = codes.astype(float)
        return out

    def predict_point(self, X: pd.DataFrame) -> np.ndarray:
        if self.model_ is None:
            raise RuntimeError("call fit() before predict_point()")
        Xf = X.reindex(columns=self.columns_, fill_value=0.0)
        curves = self.model_.predict_survival_function(Xf, return_array=True)
        times = self.model_.unique_times_
        return np.array([median_from_survival(times, c) for c in curves])

    def predict(self, X: pd.DataFrame) -> Prediction:
        """Point estimate plus a study-level bootstrap interval.

        An RSF has no analytic covariance, so the interval is bootstrapped -- resampling
        whole studies, never rows. This is genuinely expensive (n_boot forest fits); use
        `predict_point` where only a ranking is needed.
        """
        if self.model_ is None:
            raise RuntimeError("call fit() before predict()")
        unc = self.config.model.uncertainty
        if self._train is None:  # pragma: no cover - fit() always sets it
            point = self.predict_point(X)
            nan = np.full(len(X), np.nan)
            return Prediction(point=point, lower=nan, upper=nan, level=unc.level)

        Xtr, t, e, groups = self._train
        return bootstrap_interval(
            model_factory=lambda: RandomSurvivalForestEngine(self.config),
            X=Xtr, y_time=t, y_event=e, groups=groups, X_new=X,
            n_boot=unc.n_boot, level=unc.level, seed=self.config.model.cv.seed,
        )

    def feature_effects(self, n_repeats: int = 5) -> pd.DataFrame | None:
        """Permutation importance: drop in grouped-CV-free C-index when a column is shuffled.

        sksurv's RandomSurvivalForest deliberately does not expose impurity importances
        (`feature_importances_` raises), and that is the right call -- impurity importance
        is biased toward high-cardinality columns, which here would flatter continuous
        concentrations over binary context dummies. Permutation importance measures what
        the model actually loses without the column.

        Importances rank features. Unlike the AFT's time ratios they carry no direction
        and no units, so they answer "what mattered", never "by how much" -- which is why
        the Weibull AFT remains the interpretable baseline.
        """
        from sklearn.inspection import permutation_importance

        if self.model_ is None:
            raise RuntimeError("call fit() before feature_effects()")
        if self._train is None:  # pragma: no cover - fit() always sets it
            return None
        Xtr, t, e, groups = self._train
        Xf = self._augment(Xtr, groups)
        result = permutation_importance(
            self.model_,
            Xf,
            to_structured(t, e),
            n_repeats=n_repeats,
            random_state=int(self.config.model.tree_engines.rsf.get("seed", 0)),
            n_jobs=1,
        )
        return pd.DataFrame(
            {
                "feature": self.columns_,
                "importance": result.importances_mean,
                "importance_std": result.importances_std,
            }
        ).sort_values("importance", ascending=False, ignore_index=True)
