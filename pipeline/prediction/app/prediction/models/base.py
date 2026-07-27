"""The abstract survival-model interface the rest of the pipeline is agnostic to.

Adding an engine means implementing this and registering it. Nothing upstream of
`models/` knows which engine is in use, and the optimizer that will sit downstream only
ever needs :meth:`SurvivalModel.predict_conditional`.

What "uncertainty" means here
-----------------------------
Every engine returns a point estimate and an interval 

The interval is a **confidence interval on the predicted shelf life** (parameter
uncertainty), not a prediction interval for one new batch's realised failure time.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from features.builder import FeatureBuilder


@dataclass(frozen=True)
class Prediction:
    """Point estimate plus interval, in the same time units as ``t_failure`` (days)."""

    point: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    level: float = 0.95

    def __post_init__(self) -> None:
        n = len(self.point)
        if not (len(self.lower) == len(self.upper) == n):
            raise ValueError("point/lower/upper must be the same length")

    def as_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {"point": self.point, "lower": self.lower, "upper": self.upper}
        )

    @property
    def width(self) -> np.ndarray:
        return self.upper - self.lower

    def __len__(self) -> int:
        return len(self.point)


class SurvivalModel(ABC):
    """Fit / predict-with-interval / explain."""

    name: ClassVar[str] = ""
    #: Whether `feature_effects()` returns anything meaningful for this engine.
    supports_effects: ClassVar[bool] = True

    @abstractmethod
    def fit(
        self,
        X: pd.DataFrame,
        y_time: np.ndarray,
        y_event: np.ndarray,
        groups: np.ndarray | None = None,
        **kwargs: Any,
    ) -> "SurvivalModel":
        """Fit.

        `groups` carries ``experiment_ID`` per row. Studies are the effective independent
        unit, so an engine must either model them (frailty) or honour them through
        grouped CV -- never ignore them.
        """

    @abstractmethod
    def predict_point(self, X: pd.DataFrame) -> np.ndarray:
        """Predicted shelf life only -- no interval, and cheap.

        Exists because computing an interval can cost orders of magnitude more than the
        point estimate (a bootstrap refits the model hundreds of times). Cross-validation
        and the bootstrap's own inner loop need ranking, not uncertainty, so they call
        this. Without the split, a bootstrapped `predict` would recurse into itself.
        """

    @abstractmethod
    def predict(self, X: pd.DataFrame) -> Prediction:
        """Predicted shelf life with an uncertainty interval."""

    def feature_effects(self) -> pd.DataFrame | None:
        """Coefficients / importances / time ratios, where the engine has them."""
        return None

    def predict_conditional(
        self,
        builder: "FeatureBuilder",
        context: dict[str, str],
        formulation: dict[str, float],
    ) -> Prediction:
        """The optimizer's entry point.

        Given a (meat matrix, packaging) context and a candidate formulation, return the
        predicted shelf life with its interval. Implemented once here because it is the
        same for every engine: build the design row, then predict.
        """
        X = builder.transform_context(context, formulation)
        return self.predict(X)

    # -- helpers for subclasses --------------------------------------------------------

    @staticmethod
    def _validate_fit_inputs(
        X: pd.DataFrame, y_time: np.ndarray, y_event: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        t = np.asarray(y_time, dtype=float)
        e = np.asarray(y_event, dtype=int)
        if len(X) != len(t) or len(t) != len(e):
            raise ValueError("X, y_time and y_event must have the same length")
        if np.any(t <= 0):
            raise ValueError("t_failure must be strictly positive")
        if not np.isin(e, (0, 1)).all():
            raise ValueError("event must be 0 or 1")
        if e.sum() == 0:
            raise ValueError("no observed events: nothing to fit")
        return t, e
