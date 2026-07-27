"""Right-censored Weibull AFT likelihood and a group-lasso solver for it.

Kept separate from the engine so the maths can be tested directly: against finite
differences, and against `lifelines` at lambda = 0.

Model
-----
``log T = mu + sigma * W`` with ``W`` standard Gumbel(min), density ``exp(w - e^w)``. That
makes ``T`` Weibull with shape ``1/sigma``, and with ``z = (log t - mu)/sigma``::

    S(t) = exp(-e^z)                    f(t) = exp(z - e^z) / (sigma * t)

Parameterization: why not (beta, sigma)
---------------------------------------
The obvious parameterization -- AFT coefficients ``beta`` and ``log sigma`` -- makes this
objective **non-convex**, which is not a cosmetic problem for a Lasso. It breaks
``lambda_max``: the smallest penalty that zeroes every block is derived from the convex
KKT condition, and without convexity a point can satisfy that condition at ``gamma = 0``
while a strictly better non-zero optimum exists elsewhere. The lambda path would then
start somewhere arbitrary rather than at the null model. (This was observed, not
theorised: at ``lambda = 1.01 * lambda_max`` the KKT test passed at zero while FISTA found
an objective 0.1 lower.)

So we fit in the canonical location-scale parameterization instead::

    tau  = 1 / sigma          eta0 = tau * beta0          eta = tau * beta
    z_i  = tau * log t_i - eta0 - x_i' eta                      # affine in (eta0, eta, tau)

    loglik_i = event_i * (log tau - log t_i + z_i - e^z_i) + (1 - event_i) * (-e^z_i)

Here ``z`` is affine in the parameters, ``-e^z`` is concave, and ``log tau`` is concave, so
the log-likelihood is **jointly concave** in ``(eta0, eta, tau)`` on ``tau > 0``
(Burridge 1981; Kalbfleisch & Prentice). FISTA then has a global optimum to find and
``lambda_max`` is exact.

Selection is unaffected by the change of variables -- ``eta_g = 0`` exactly when
``beta_g = 0``, because ``tau > 0`` -- so the penalty still answers the question we care
about ("does this ingredient matter?"). It does shift *what* is penalized from ``beta`` to
``beta / sigma``, i.e. effect sizes measured in units of the error scale. That is the
usual and arguably the more sensible object to shrink; it is called out here because it is
a real modelling choice, not an implementation detail.

Why a group penalty rather than a flat Lasso
--------------------------------------------
Ingredient features, pillar features and their interactions are correlated and
group-structured. A flat per-coefficient Lasso would happily keep ``thymol x fish`` while
dropping ``thymol``, or select one arbitrary dummy out of a categorical, producing a model
nobody can act on. The group penalty ``lambda * sum_g sqrt(p_g) * ||eta_g||_2`` selects or
drops an ingredient together with all of its own interactions, and treats a categorical's
dummies as one decision. The ``sqrt(p_g)`` weight is the standard Yuan & Lin correction so
larger blocks are not penalized merely for being larger.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

#: exp(z) overflows near z = 709; clipping stops one wild iterate turning the objective
#: into inf/nan and killing an otherwise healthy optimization.
_Z_CLIP = 50.0
#: tau = 1/sigma must stay strictly positive (log tau appears in the likelihood).
_TAU_MIN = 1e-6


# -- likelihood in the canonical (eta0, eta, tau) parameterization ----------------------


def _z(theta: np.ndarray, X: np.ndarray, log_t: np.ndarray) -> np.ndarray:
    eta0, eta, tau = theta[0], theta[1:-1], theta[-1]
    return np.clip(tau * log_t - eta0 - X @ eta, -_Z_CLIP, _Z_CLIP)


def neg_loglik(
    theta: np.ndarray, X: np.ndarray, log_t: np.ndarray, event: np.ndarray
) -> float:
    """Mean negative log-likelihood. ``theta = [eta0, eta..., tau]``."""
    tau = theta[-1]
    if tau <= 0:
        return np.inf
    z = _z(theta, X, log_t)
    ez = np.exp(z)
    ll = event * (np.log(tau) - log_t + z - ez) + (1 - event) * (-ez)
    return float(-ll.sum() / len(log_t))


def neg_loglik_grad(
    theta: np.ndarray, X: np.ndarray, log_t: np.ndarray, event: np.ndarray
) -> np.ndarray:
    """Analytic gradient of :func:`neg_loglik`.

    With ``r_i = event_i - e^z_i``::

        d loglik / d eta0 = -r_i
        d loglik / d eta  = -r_i * x_i
        d loglik / d tau  =  event_i / tau + r_i * log t_i
    """
    n = len(log_t)
    tau = theta[-1]
    z = _z(theta, X, log_t)
    r = event - np.exp(z)

    g = np.empty_like(theta)
    g[0] = r.sum() / n
    g[1:-1] = X.T @ r / n
    g[-1] = -(np.sum(event) / max(tau, _TAU_MIN) + float(r @ log_t)) / n
    return g


# -- conversions ------------------------------------------------------------------------


@dataclass(frozen=True)
class AFTParams:
    """The interpretable AFT view of a canonical fit."""

    intercept: float   # beta0
    coef: np.ndarray   # beta -- log-time-ratio per unit of X
    sigma: float       # AFT scale; Weibull shape = 1/sigma

    @property
    def shape(self) -> float:
        return 1.0 / self.sigma

    def time_ratios(self) -> np.ndarray:
        """exp(beta_j): multiplicative effect on shelf life per unit of feature j."""
        return np.exp(self.coef)

    def linear_predictor(self, X: np.ndarray) -> np.ndarray:
        return self.intercept + X @ self.coef


def to_aft(theta: np.ndarray) -> AFTParams:
    """Map canonical ``(eta0, eta, tau)`` back to AFT ``(beta0, beta, sigma)``."""
    eta0, eta, tau = theta[0], theta[1:-1], theta[-1]
    return AFTParams(intercept=float(eta0 / tau), coef=eta / tau, sigma=float(1.0 / tau))


def from_aft(intercept: float, coef: np.ndarray, sigma: float) -> np.ndarray:
    tau = 1.0 / sigma
    return np.concatenate([[intercept * tau], coef * tau, [tau]])


def _init_theta(X: np.ndarray, log_t: np.ndarray) -> np.ndarray:
    tau0 = 1.0 / max(float(np.std(log_t)), 1e-2)
    return np.concatenate([[tau0 * float(np.mean(log_t))], np.zeros(X.shape[1]), [tau0]])


# -- fitting ----------------------------------------------------------------------------


def fit_unpenalized(
    X: np.ndarray, t: np.ndarray, event: np.ndarray, theta0: np.ndarray | None = None
) -> tuple[np.ndarray, float]:
    """Plain MLE. Returns ``(theta, neg_loglik)`` in canonical parameters."""
    log_t = np.log(t)
    theta0 = _init_theta(X, log_t) if theta0 is None else theta0.copy()
    bounds = [(None, None)] * (X.shape[1] + 1) + [(_TAU_MIN, None)]
    res = minimize(
        neg_loglik,
        theta0,
        args=(X, log_t, event),
        jac=neg_loglik_grad,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 5000, "ftol": 1e-14, "gtol": 1e-12},
    )
    return res.x, float(res.fun)


def group_weights(groups: np.ndarray) -> np.ndarray:
    """sqrt(block size), indexed by group id."""
    uniq = np.unique(groups)
    w = np.zeros(int(uniq.max()) + 1)
    for g in uniq:
        w[g] = np.sqrt(int((groups == g).sum()))
    return w


def _prox(
    theta: np.ndarray, groups: np.ndarray, step_lambda: float, weights: np.ndarray
) -> np.ndarray:
    """Proximal step: block soft-threshold on eta, positivity projection on tau.

    eta0 and tau are never penalized -- shrinking them would distort baseline shelf life
    and the Weibull shape, which are not variable-selection decisions.
    """
    out = theta.copy()
    eta = out[1:-1]
    for g in np.unique(groups):
        idx = groups == g
        norm = float(np.linalg.norm(eta[idx]))
        if norm <= 0:
            eta[idx] = 0.0
            continue
        eta[idx] = eta[idx] * max(1.0 - (step_lambda * weights[g]) / norm, 0.0)
    out[1:-1] = eta
    out[-1] = max(out[-1], _TAU_MIN)
    return out


@dataclass
class GroupLassoFit:
    theta: np.ndarray
    objective: float
    n_iter: int
    converged: bool

    @property
    def eta(self) -> np.ndarray:
        return self.theta[1:-1]

    @property
    def tau(self) -> float:
        return float(self.theta[-1])

    def aft(self) -> AFTParams:
        return to_aft(self.theta)


def penalty_value(
    theta: np.ndarray, groups: np.ndarray, lam: float, weights: np.ndarray
) -> float:
    eta = theta[1:-1]
    return lam * sum(
        weights[g] * float(np.linalg.norm(eta[groups == g])) for g in np.unique(groups)
    )


def lambda_max(X: np.ndarray, t: np.ndarray, event: np.ndarray, groups: np.ndarray) -> float:
    """Smallest lambda that zeroes every block.

    Evaluated at the intercept-only optimum, where eta = 0 and (eta0, tau) are at their
    MLE. Because the canonical objective is convex, the KKT condition
    ``||grad_g|| <= lambda * w_g for all g`` is not just necessary but sufficient, so this
    value is exact rather than a heuristic.
    """
    log_t = np.log(t)
    theta_null, _ = fit_unpenalized(np.zeros((len(t), 0)), t, event)
    theta = np.concatenate([[theta_null[0]], np.zeros(X.shape[1]), [theta_null[-1]]])
    g = neg_loglik_grad(theta, X, log_t, event)[1:-1]
    w = group_weights(groups)
    return max(
        float(np.linalg.norm(g[groups == gi]) / w[gi]) for gi in np.unique(groups)
    )


def fit_group_lasso(
    X: np.ndarray,
    t: np.ndarray,
    event: np.ndarray,
    groups: np.ndarray,
    lam: float,
    theta0: np.ndarray | None = None,
    max_iter: int = 2000,
    tol: float = 1e-7,
) -> GroupLassoFit:
    """FISTA with backtracking line search on the penalized canonical objective."""
    log_t = np.log(t)
    w = group_weights(groups)
    theta = _init_theta(X, log_t) if theta0 is None else theta0.copy()
    theta[-1] = max(theta[-1], _TAU_MIN)

    def objective(th: np.ndarray) -> float:
        return neg_loglik(th, X, log_t, event) + penalty_value(th, groups, lam, w)

    y = theta.copy()
    t_k = 1.0
    L = 1.0
    converged = False
    it = 0

    for it in range(1, max_iter + 1):
        f_y = neg_loglik(y, X, log_t, event)
        g_y = neg_loglik_grad(y, X, log_t, event)

        cand = theta
        for _ in range(80):
            step = 1.0 / L
            cand = _prox(y - step * g_y, groups, step * lam, w)
            diff = cand - y
            f_cand = neg_loglik(cand, X, log_t, event)
            if np.isfinite(f_cand) and f_cand <= f_y + g_y @ diff + 0.5 * L * (diff @ diff) + 1e-12:
                break
            L *= 2.0
        else:  # pragma: no cover - only on pathological input
            break

        t_new = 0.5 * (1.0 + np.sqrt(1.0 + 4.0 * t_k * t_k))
        y = cand + ((t_k - 1.0) / t_new) * (cand - theta)
        shift = float(np.linalg.norm(cand - theta))
        theta, t_k = cand, t_new

        if shift <= tol * (1.0 + float(np.linalg.norm(theta))):
            converged = True
            break
        L = max(L * 0.9, 1e-8)  # let the step grow back after a hard iteration

    return GroupLassoFit(
        theta=theta, objective=objective(theta), n_iter=it, converged=converged
    )


def lambda_path(
    X: np.ndarray,
    t: np.ndarray,
    event: np.ndarray,
    groups: np.ndarray,
    n_lambda: int = 25,
    lambda_min_ratio: float = 0.01,
) -> np.ndarray:
    """Geometric path from `lambda_max` (null model) down to a near-full model."""
    lmax = lambda_max(X, t, event, groups)
    return np.geomspace(lmax, lmax * lambda_min_ratio, n_lambda)


def selected_groups(
    eta: np.ndarray, groups: np.ndarray, tol: float = 1e-8
) -> list[int]:
    """Group ids whose block survived the penalty."""
    return [
        int(g)
        for g in np.unique(groups)
        if float(np.linalg.norm(eta[groups == g])) > tol
    ]
