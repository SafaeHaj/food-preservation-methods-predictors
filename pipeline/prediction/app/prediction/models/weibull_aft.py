"""Weibull AFT baseline: the primary, interpretable engine.

Two stages, because no single library does both halves honestly:

**Stage 1 (Python).** Study-grouped group-Lasso selection over the expanded feature set,
on the right-censored Weibull AFT likelihood, solved with FISTA. `lifelines` has a
penalizer but it is elastic-net per coefficient, not a group penalty, so it would happily
keep `thymol x fish` while dropping `thymol`.

**Stage 2 (R).** `frailtypack::frailtyPenal(..., hazard="Weibull", RandDist="Gamma")` refits
the surviving features with a shared study frailty. Two things worth saying plainly:

* `lifelines` has **no native AFT frailty**, which is why stage 2 leaves Python at all.
* frailtypack's "penalized likelihood" is **baseline-hazard spline smoothing, not covariate
  Lasso** -- so it cannot do stage 1's job, and stage 1 cannot do its job. Neither stage is
  redundant.
* frailtyPenal fits **proportional hazards**, not AFT. Weibull is the unique distribution
  that is both, so PH coefficients convert exactly: `time_ratio = exp(-beta_PH / shape)`.

Effects are reported as **time ratios** `exp(gamma_j)`: a ratio of 1.20 means 20% longer
shelf life per unit of that feature.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from app.core.config import Config
from app.prediction.models import weibull_likelihood as wl
from app.prediction.models.base import Prediction, SurvivalModel
from app.prediction.models.cv import grouped_folds, iter_fold_assignments
from app.prediction.models.r_frailty import FrailtyFit, RNotAvailableError, run_frailty_fit

#: log(log 2). The Weibull median solves S(t) = 0.5, i.e. z = log(log 2).
_LOG_LOG2 = float(np.log(np.log(2.0)))


class WeibullAFTEngine(SurvivalModel):
    """Group-Lasso selection, then a shared-frailty refit.

    The point estimate is the **median** time to failure -- the time by which half the
    batches of this formulation have failed. Median rather than mean because it is the
    quantity a shelf-life date actually encodes, and it is robust to the Weibull's right
    tail.
    """

    name = "weibull_aft"

    def __init__(
        self,
        config: Config,
        feature_groups: np.ndarray | None = None,
        group_names: list[str] | None = None,
    ) -> None:
        self.config = config
        self.feature_groups = feature_groups
        self.group_names = group_names

        self.columns_: list[str] = []
        self.selected_columns_: list[str] = []
        self.lambda_: float | None = None
        self.lambda_path_: np.ndarray | None = None
        self.cv_curve_: pd.DataFrame | None = None
        self.stage1_: wl.GroupLassoFit | None = None
        self.stage1_refit_: wl.AFTParams | None = None
        self.frailty_: FrailtyFit | None = None
        self.stage2_used_: bool = False
        self.stage2_skip_reason_: str | None = None
        self._cov_stage1_: np.ndarray | None = None
        self._theta_stage1_: np.ndarray | None = None

    # -- fit ---------------------------------------------------------------------------

    def fit(
        self,
        X: pd.DataFrame,
        y_time: np.ndarray,
        y_event: np.ndarray,
        groups: np.ndarray | None = None,
        **kwargs: Any,
    ) -> "WeibullAFTEngine":
        t, e = self._validate_fit_inputs(X, y_time, y_event)
        self.columns_ = list(X.columns)
        Xa = X.to_numpy(dtype=float)

        fgroups = self.feature_groups
        if fgroups is None:
            # Each column its own block: the penalty degenerates to a plain Lasso. Legal,
            # but not what the spec asks for -- callers should pass the builder's vector.
            fgroups = np.arange(Xa.shape[1])
        fgroups = np.asarray(fgroups)

        cfg = self.config.model.weibull_aft
        path = wl.lambda_path(
            Xa, t, e, fgroups,
            n_lambda=cfg.lambda_path_length,
            lambda_min_ratio=cfg.lambda_min_ratio,
        )
        self.lambda_path_ = path

        if groups is not None and len(pd.unique(np.asarray(groups))) >= 2:
            self.lambda_, self.cv_curve_ = self._select_lambda(Xa, t, e, fgroups, groups, path)
        else:
            # Without study structure there is nothing to cross-validate against; take the
            # least-penalized model rather than inventing a fold split.
            self.lambda_ = float(path[-1])

        self.stage1_ = wl.fit_group_lasso(
            Xa, t, e, fgroups, lam=self.lambda_,
            max_iter=cfg.max_iter, tol=cfg.tol,
        )
        keep_groups = wl.selected_groups(self.stage1_.eta, fgroups)
        keep_mask = np.isin(fgroups, keep_groups)
        self.selected_columns_ = [c for c, k in zip(self.columns_, keep_mask, strict=True) if k]

        # Unpenalized refit on the survivors: Lasso coefficients are shrunk by
        # construction, so reporting them as effect sizes would understate every one.
        Xs = Xa[:, keep_mask] if keep_mask.any() else np.zeros((len(t), 0))
        theta_refit, _ = wl.fit_unpenalized(Xs, t, e)
        self._theta_stage1_ = theta_refit
        self.stage1_refit_ = wl.to_aft(theta_refit)
        self._cov_stage1_ = _observed_covariance(theta_refit, Xs, np.log(t), e)

        self.stage2_used_ = False
        self.stage2_skip_reason_ = None
        if cfg.use_r_frailty:
            self._fit_stage2(X, keep_mask, t, e, groups)
        else:
            self.stage2_skip_reason_ = "model.weibull_aft.use_r_frailty is false"
        return self

    def _fit_stage2(
        self,
        X: pd.DataFrame,
        keep_mask: np.ndarray,
        t: np.ndarray,
        e: np.ndarray,
        groups: np.ndarray | None,
    ) -> None:
        if not keep_mask.any():
            self.stage2_skip_reason_ = "stage 1 selected no features"
            return
        if groups is None:
            self.stage2_skip_reason_ = "no experiment_ID groups supplied; frailty needs them"
            return
        # frailtypack estimates a between-study variance; with one study there is none.
        if len(pd.unique(np.asarray(groups))) < 2:
            self.stage2_skip_reason_ = "fewer than 2 studies"
            return
        try:
            self.frailty_ = run_frailty_fit(
                X.loc[:, self.selected_columns_], t, e, np.asarray(groups),
                folds=None, config=self.config.r,
            )
            self.stage2_used_ = self.frailty_.converged
            if not self.frailty_.converged:
                self.stage2_skip_reason_ = "frailtyPenal did not converge (istop != 1)"
        except (RNotAvailableError, RuntimeError) as exc:
            # Surface rather than swallow: R was chosen deliberately, and silently
            # returning a frailty-free model that looks fine is the worst outcome here.
            self.stage2_skip_reason_ = f"{type(exc).__name__}: {exc}"
            raise

    def _select_lambda(
        self,
        X: np.ndarray,
        t: np.ndarray,
        e: np.ndarray,
        fgroups: np.ndarray,
        groups: np.ndarray,
        path: np.ndarray,
    ) -> tuple[float, pd.DataFrame]:
        """Pick lambda by study-grouped CV on held-out log-likelihood.

        Held-out deviance rather than C-index: it scores the calibration of the whole
        fitted distribution, and the AFT's job here is to produce believable *times* with
        intervals, not just a correct ranking.
        """
        cv = self.config.model.cv
        folds = grouped_folds(groups, n_splits=cv.n_splits, seed=cv.seed)
        rows = []
        for lam in path:
            fold_scores = []
            for tr, te in folds:
                if e[tr].sum() == 0 or e[te].sum() == 0:
                    continue
                fit = wl.fit_group_lasso(
                    X[tr], t[tr], e[tr], fgroups, lam=lam,
                    max_iter=self.config.model.weibull_aft.max_iter,
                    tol=self.config.model.weibull_aft.tol,
                )
                fold_scores.append(
                    wl.neg_loglik(fit.theta, X[te], np.log(t[te]), e[te])
                )
            rows.append(
                {
                    "lambda": float(lam),
                    "mean_heldout_nll": float(np.mean(fold_scores)) if fold_scores else np.nan,
                    "n_folds": len(fold_scores),
                }
            )
        curve = pd.DataFrame(rows)
        if curve["mean_heldout_nll"].isna().all():
            return float(path[-1]), curve
        best = float(curve.loc[curve["mean_heldout_nll"].idxmin(), "lambda"])
        return best, curve

    # -- predict -----------------------------------------------------------------------

    def predict_point(self, X: pd.DataFrame) -> np.ndarray:
        """Median shelf life, no interval. Cheap: the delta method is skipped."""
        if self.stage1_refit_ is None:
            raise RuntimeError("call fit() before predict_point()")
        Xs = self._selected_matrix(X)
        if self.stage2_used_ and self.frailty_ is not None:
            f = self.frailty_
            theta = max(f.theta, 1e-12)
            h_med = np.expm1(theta * np.log(2.0)) / theta
            return np.exp(np.log(f.scale) + (np.log(h_med) - Xs @ f.beta_ph) / f.shape)
        assert self._theta_stage1_ is not None
        th = self._theta_stage1_
        return np.exp((th[0] + Xs @ th[1:-1] + _LOG_LOG2) / th[-1])

    def predict(self, X: pd.DataFrame) -> Prediction:
        if self.stage1_refit_ is None:
            raise RuntimeError("call fit() before predict()")
        level = self.config.model.uncertainty.level
        if self.stage2_used_ and self.frailty_ is not None:
            return self._predict_stage2(X, level)
        return self._predict_stage1(X, level)

    def _predict_stage1(self, X: pd.DataFrame, level: float) -> Prediction:
        assert self._theta_stage1_ is not None and self._cov_stage1_ is not None
        Xs = self._selected_matrix(X)
        theta = self._theta_stage1_
        eta0, eta, tau = theta[0], theta[1:-1], theta[-1]

        # log t_med = (eta0 + x'eta + log log 2) / tau
        num = eta0 + Xs @ eta + _LOG_LOG2
        log_med = num / tau

        # Delta method: J = [d/d eta0, d/d eta, d/d tau].
        n = len(Xs)
        J = np.empty((n, len(theta)))
        J[:, 0] = 1.0 / tau
        J[:, 1:-1] = Xs / tau
        J[:, -1] = -num / (tau**2)
        var = np.einsum("ij,jk,ik->i", J, self._cov_stage1_, J)
        return _interval_from_log(log_med, var, level)

    def _predict_stage2(self, X: pd.DataFrame, level: float) -> Prediction:
        """Population-averaged (marginal) median for a *new*, unseen study.

        For a shared gamma frailty PH model the frailty integrates out in closed form::

            S(t|x) = (1 + theta * (t/b)^a * e^{x'beta})^(-1/theta)

        so the median solves ``(t/b)^a e^{x'beta} = (2^theta - 1)/theta``, which tends to
        ``log 2`` as theta -> 0 and so degrades gracefully to the frailty-free median.
        Marginal rather than conditional because the optimizer asks about a formulation in
        general, not about one study we happen to have seen.
        """
        f = self.frailty_
        assert f is not None
        Xs = self._selected_matrix(X)
        lp = Xs @ f.beta_ph

        theta = max(f.theta, 1e-12)
        # (2^theta - 1)/theta, via expm1 for stability at small theta.
        h_med = np.expm1(theta * np.log(2.0)) / theta
        log_med = np.log(f.scale) + (np.log(h_med) - lp) / f.shape

        # d log t_med / d beta = -x / a. Treats the Weibull shape/scale and theta as known;
        # the beta covariance is the dominant term and is what frailtypack reports (varH).
        var = np.einsum("ij,jk,ik->i", Xs, f.vcov_ph, Xs) / (f.shape**2)
        return _interval_from_log(log_med, var, level)

    def _selected_matrix(self, X: pd.DataFrame) -> np.ndarray:
        missing = [c for c in self.selected_columns_ if c not in X.columns]
        if missing:
            raise ValueError(f"X is missing selected column(s): {missing}")
        if not self.selected_columns_:
            return np.zeros((len(X), 0))
        return X.loc[:, self.selected_columns_].to_numpy(dtype=float)

    # -- effects -----------------------------------------------------------------------

    def feature_effects(self, scales: pd.Series | None = None) -> pd.DataFrame:
        """Ranked time ratios.

        `scales` is the builder's per-column standard deviation. Engines fit on
        standardized columns, so without it the effects read "per 1 SD"; with it they read
        per original unit (per 1% w/w), which is what a food scientist can act on.
        """
        if self.stage1_refit_ is None:
            raise RuntimeError("call fit() before feature_effects()")

        if self.stage2_used_ and self.frailty_ is not None:
            terms = self.frailty_.terms
            coef = self.frailty_.aft_coef()
            se_aft = np.sqrt(np.diag(self.frailty_.vcov_ph)) / self.frailty_.shape
            stage = "stage2_frailty"
        else:
            terms = self.selected_columns_
            coef = self.stage1_refit_.coef
            se_aft = self._stage1_coef_se()
            stage = "stage1_refit"

        group_of = self._group_lookup()
        out = pd.DataFrame(
            {
                "feature": terms,
                "group": [group_of.get(c, "") for c in terms],
                "stage": stage,
                "coef_log_time_ratio": coef,
                "time_ratio_per_sd": np.exp(coef),
                "se": se_aft,
            }
        )
        z = norm.ppf(1 - (1 - self.config.model.uncertainty.level) / 2)
        out["ci_low_per_sd"] = np.exp(coef - z * se_aft)
        out["ci_high_per_sd"] = np.exp(coef + z * se_aft)

        if scales is not None:
            s = scales.reindex(out["feature"]).to_numpy(dtype=float)
            out["coef_per_unit"] = out["coef_log_time_ratio"] / s
            out["time_ratio_per_unit"] = np.exp(out["coef_per_unit"])

        out["abs_effect"] = out["coef_log_time_ratio"].abs()
        return out.sort_values("abs_effect", ascending=False, ignore_index=True).drop(
            columns="abs_effect"
        )

    def _stage1_coef_se(self) -> np.ndarray:
        """Delta-method SEs for beta = eta/tau from the canonical covariance."""
        assert self._theta_stage1_ is not None and self._cov_stage1_ is not None
        theta = self._theta_stage1_
        tau = theta[-1]
        p = len(theta) - 2
        se = np.empty(p)
        for j in range(p):
            J = np.zeros(len(theta))
            J[1 + j] = 1.0 / tau
            J[-1] = -theta[1 + j] / tau**2
            se[j] = float(np.sqrt(max(J @ self._cov_stage1_ @ J, 0.0)))
        return se

    def _group_lookup(self) -> dict[str, str]:
        if self.feature_groups is None or self.group_names is None:
            return {}
        return {
            col: self.group_names[g]
            for col, g in zip(self.columns_, np.asarray(self.feature_groups), strict=True)
        }

    def selection_summary(self) -> pd.DataFrame:
        """Which blocks survived stage 1 -- the group penalty's actual decisions."""
        if self.stage1_ is None or self.feature_groups is None or self.group_names is None:
            raise RuntimeError("call fit() with feature_groups before selection_summary()")
        fg = np.asarray(self.feature_groups)
        kept = set(wl.selected_groups(self.stage1_.eta, fg))
        rows = [
            {
                "group": self.group_names[g],
                "n_columns": int((fg == g).sum()),
                "selected": g in kept,
                "block_norm": float(np.linalg.norm(self.stage1_.eta[fg == g])),
            }
            for g in range(len(self.group_names))
        ]
        return pd.DataFrame(rows).sort_values(
            ["selected", "block_norm"], ascending=[False, False], ignore_index=True
        )

    def r_fold_assignments(self, groups: np.ndarray) -> np.ndarray:
        """Fold column for the R bridge, so its CV loop runs inside one R call."""
        cv = self.config.model.cv
        return iter_fold_assignments(groups, n_splits=cv.n_splits, seed=cv.seed)


# -- helpers ----------------------------------------------------------------------------


def _interval_from_log(log_med: np.ndarray, var: np.ndarray, level: float) -> Prediction:
    z = norm.ppf(1 - (1 - level) / 2)
    sd = np.sqrt(np.clip(var, 0.0, None))
    return Prediction(
        point=np.exp(log_med),
        lower=np.exp(log_med - z * sd),
        upper=np.exp(log_med + z * sd),
        level=level,
    )


def _observed_covariance(
    theta: np.ndarray, X: np.ndarray, log_t: np.ndarray, event: np.ndarray
) -> np.ndarray:
    """Inverse observed information, by finite differences of the analytic gradient.

    `neg_loglik` is the *mean*, so the observed information is n * Hessian(mean).
    """
    n = len(log_t)
    p = len(theta)
    H = np.zeros((p, p))
    eps = 1e-5
    for j in range(p):
        step = np.zeros(p)
        step[j] = eps
        gp = wl.neg_loglik_grad(theta + step, X, log_t, event)
        gm = wl.neg_loglik_grad(theta - step, X, log_t, event)
        H[:, j] = (gp - gm) / (2 * eps)
    H = 0.5 * (H + H.T) * n
    try:
        return np.linalg.inv(H)
    except np.linalg.LinAlgError:
        # Near-singular information (a feature with almost no support) -- pinv keeps the
        # interval finite and wide rather than crashing the run.
        return np.linalg.pinv(H)
