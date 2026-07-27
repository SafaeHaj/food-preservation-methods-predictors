"""
Kinetic model fitting service.

Fits Baranyi-Roberts, Modified Gompertz, Weibull Inactivation, and Geeraerd
models to microbial growth/inactivation trajectories using scipy nonlinear
least squares.  Computes MAE, RMSE, R², adj-R², AIC, BIC, AICc, and
(optionally) t_failure by numerical root finding.

Process routing:
  - Growth trajectories  → Baranyi-Roberts, Modified Gompertz
  - Inactivation trajectories → Weibull Inactivation, Geeraerd
  - Stable / insufficient → all models skipped
"""
from __future__ import annotations

import warnings
from typing import Any

import numpy as np
from scipy.optimize import curve_fit, brentq

from shared.errors import ValidationError

warnings.filterwarnings("ignore", category=RuntimeWarning)

# ─── Model functions (all log₁₀ units) ───────────────────────────────────────

def _baranyi(t: np.ndarray, N0: float, Nmax: float, mumax: float, lag: float) -> np.ndarray:
    """Baranyi-Roberts growth model (Zwietering formulation, log₁₀ CFU/g)."""
    h0 = mumax * lag
    arg     = np.clip(-mumax * t, -700, 0)
    h0c     = np.clip(-h0, -700, 0)
    combined = np.clip(-mumax * t - h0, -700, 0)
    A = t + (1.0 / mumax) * np.log(
        np.exp(arg) + np.exp(h0c) - np.exp(combined)
    )
    inner = 1.0 + (10.0 ** (Nmax - N0) - 1.0) * np.exp(np.clip(-mumax * A, -700, 700))
    return Nmax - np.log10(np.maximum(inner, 1e-30))


def _gompertz(t: np.ndarray, N0: float, A: float, mumax: float, lag: float) -> np.ndarray:
    """Modified Gompertz growth model (Zwietering 1990, log₁₀ CFU/g)."""
    exponent = mumax * np.e / np.maximum(A, 1e-9) * (lag - t) + 1.0
    return N0 + A * np.exp(-np.exp(exponent))


def _weibull(t: np.ndarray, N0: float, delta: float, p: float) -> np.ndarray:
    """Weibull inactivation model (log₁₀ CFU/g)."""
    return N0 - (np.maximum(t, 0) / np.maximum(delta, 1e-9)) ** p


def _geeraerd(t: np.ndarray, N0: float, Nres: float, kmax: float, Sl: float) -> np.ndarray:
    """Geeraerd inactivation model (log₁₀ CFU/g)."""
    Cc0   = np.exp(np.clip(kmax * Sl, 0, 500)) - 1.0
    N_lin = (10.0 ** N0 - 10.0 ** Nres) * np.exp(np.clip(-kmax * t, -700, 0))
    shield = np.exp(np.clip(kmax * Sl, 0, 500)) / (
        np.exp(np.clip(kmax * Sl, 0, 500)) + Cc0 * (1.0 - np.exp(np.clip(-kmax * t, -700, 0)))
    )
    Nt = N_lin * shield + 10.0 ** Nres
    return np.log10(np.maximum(Nt, 1e-10))


# ─── Model registry ───────────────────────────────────────────────────────────
# bounds_fn and p0_guess now accept (t_obs, y_obs) so time-based parameters
# (lag, shoulder, delta) are bounded relative to the actual observation window.

KINETIC_MODELS: dict[str, dict] = {
    "baranyi": {
        "func":        _baranyi,
        "param_names": ["N0", "Nmax", "mumax", "lag"],
        "p0_guess":    lambda t, y: [y[0], y.max(), 0.1, (t.max() - t.min()) * 0.15],
        "bounds_fn":   lambda t, y: (
            [y.min() - 3, y.min(), 1e-4, 0.0],
            [y.max() + 3, y.max() + 3, 5.0, float(t.max())],
        ),
        "min_points": 5,
        "process":    "growth",
    },
    "gompertz": {
        "func":        _gompertz,
        "param_names": ["N0", "A", "mumax", "lag"],
        "p0_guess":    lambda t, y: [y[0], max(y.max() - y.min(), 0.5), 0.1, (t.max() - t.min()) * 0.15],
        "bounds_fn":   lambda t, y: (
            [y.min() - 3, 0.01, 1e-4, 0.0],
            [y.max() + 3, (y.max() - y.min()) * 2 + 1, 5.0, float(t.max())],
        ),
        "min_points": 4,
        "process":    "growth",
    },
    "weibull_inact": {
        "func":        _weibull,
        "param_names": ["N0", "delta", "p"],
        "p0_guess":    lambda t, y: [y[0], (t.max() - t.min()) * 0.3, 1.0],
        "bounds_fn":   lambda t, y: (
            [y.min() - 2, 1e-6, 0.1],
            [y.max() + 3, float(t.max()) * 10, 10.0],
        ),
        "min_points": 4,
        "process":    "inactivation",
    },
    "geeraerd": {
        "func":        _geeraerd,
        "param_names": ["N0", "Nres", "kmax", "Sl"],
        "p0_guess":    lambda t, y: [y[0], y.min(), 0.5, (t.max() - t.min()) * 0.15],
        "bounds_fn":   lambda t, y: (
            [y.min() - 3, y.min() - 3, 1e-4, 0.0],
            [y.max() + 3, y.max() + 1, 20.0, float(t.max())],
        ),
        "min_points": 5,
        "process":    "inactivation",
    },
}

# ─── Trajectory classification ────────────────────────────────────────────────

def _classify_trajectory(t_obs: np.ndarray, y_obs: np.ndarray) -> str:
    """
    Classify a trajectory as 'growth', 'inactivation', or 'stable'.

    Uses the total signed change in log₁₀ CFU from the first to last
    observation (sorted by time).  A change of ≥ 0.5 log is well above
    normal measurement noise (~0.2 log) for microbiological counting.
    """
    if len(y_obs) < 2:
        return "insufficient"
    order = np.argsort(t_obs)
    y_sorted = y_obs[order]
    delta = float(y_sorted[-1]) - float(y_sorted[0])
    if delta >= 0.5:
        return "growth"
    if delta <= -0.5:
        return "inactivation"
    return "stable"


# ─── Metrics ──────────────────────────────────────────────────────────────────

def _compute_metrics(
    y_obs: np.ndarray, y_pred: np.ndarray, n_params: int
) -> dict[str, float | None]:
    n = len(y_obs)
    residuals = y_obs - y_pred
    ss_res = np.sum(residuals ** 2)
    ss_tot = np.sum((y_obs - y_obs.mean()) ** 2)

    mae  = float(np.mean(np.abs(residuals)))
    rmse = float(np.sqrt(ss_res / n))
    r2   = float(1.0 - ss_res / ss_tot) if ss_tot > 1e-12 else None
    k    = n_params

    if r2 is not None and n > k + 1:
        adj_r2 = float(1.0 - (1.0 - r2) * (n - 1) / (n - k - 1))
    else:
        adj_r2 = None

    if ss_res > 0 and n > k:
        sigma2 = ss_res / n
        ll   = -n / 2.0 * np.log(2 * np.pi * sigma2) - ss_res / (2.0 * sigma2)
        aic  = float(2 * k - 2 * ll)
        bic  = float(k * np.log(n) - 2 * ll)
        aicc = float(aic + 2 * k * (k + 1) / (n - k - 1)) if n > k + 1 else None
    else:
        aic = bic = aicc = None

    return {"mae": mae, "rmse": rmse, "r2": r2, "adj_r2": adj_r2,
            "aic": aic, "bic": bic, "aicc": aicc}


def _loo_error(
    t_obs: np.ndarray,
    y_obs: np.ndarray,
    model_func,
    params: np.ndarray,
    bounds,
) -> dict[str, float] | None:
    """Leave-one-time-point-out CV (only when n >= 6)."""
    n = len(t_obs)
    if n < 6:
        return None
    errors = []
    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False
        try:
            popt, _ = curve_fit(
                model_func, t_obs[mask], y_obs[mask],
                p0=params, bounds=bounds, maxfev=3000,
            )
            pred = model_func(t_obs[i:i+1], *popt)[0]
            errors.append(abs(y_obs[i] - pred))
        except Exception:
            pass
    if not errors:
        return None
    return {
        "loo_mae":  float(np.mean(errors)),
        "loo_rmse": float(np.sqrt(np.mean(np.array(errors) ** 2))),
    }


def _estimate_t_failure(
    model_func,
    params: list,
    threshold: float,
    t_max: float,
    process: str,
) -> float | None:
    """
    Find the time when the model curve crosses the safety threshold.

    Growth models:     search for the first upward crossing (N increases past threshold).
    Inactivation models: search for the first downward crossing (N falls below threshold).
    """
    try:
        t_search = np.linspace(0, t_max * 3, 5000)
        y_search = model_func(t_search, *params)
        diff_sign = np.diff(np.sign(y_search - threshold))

        if process == "growth":
            # y rises through threshold: sign goes from negative to positive
            crossings = np.where(diff_sign > 0)[0]
        else:
            # y falls through threshold: sign goes from positive to negative
            crossings = np.where(diff_sign < 0)[0]

        if len(crossings) == 0:
            return None
        i = crossings[0]
        t_lo, t_hi = t_search[i], t_search[i + 1]
        return float(
            brentq(lambda t: model_func(np.array([t]), *params)[0] - threshold, t_lo, t_hi)
        )
    except Exception:
        return None


def _bootstrap_t_failure(
    t_obs: np.ndarray,
    y_obs: np.ndarray,
    model_func,
    params: np.ndarray,
    bounds,
    threshold: float,
    t_max: float,
    process: str,
    n_boot: int = 100,
) -> dict[str, float] | None:
    n = len(t_obs)
    if n < 4:
        return None
    tf_boot = []
    for _ in range(n_boot):
        idx = np.random.choice(n, n, replace=True)
        try:
            popt, _ = curve_fit(
                model_func, t_obs[idx], y_obs[idx],
                p0=params, bounds=bounds, maxfev=3000,
            )
            tf = _estimate_t_failure(model_func, list(popt), threshold, t_max, process)
            if tf is not None:
                tf_boot.append(tf)
        except Exception:
            pass
    if len(tf_boot) < 10:
        return None
    arr = np.array(tf_boot)
    return {
        "t_failure_ci_lo":  float(np.percentile(arr, 2.5)),
        "t_failure_ci_hi":  float(np.percentile(arr, 97.5)),
        "t_failure_median": float(np.median(arr)),
    }


# ─── Fit one trajectory with eligible models ──────────────────────────────────

def fit_trajectory(
    t_obs: np.ndarray,
    y_obs: np.ndarray,
    trajectory_id: str,
    threshold: float | None = None,
) -> dict[str, Any]:
    """
    Classify the trajectory, then fit only the biologically appropriate models.

    Growth trajectories  → Baranyi-Roberts, Modified Gompertz
    Inactivation trajectories → Weibull Inactivation, Geeraerd
    Stable / insufficient → all models skipped with reason
    """
    t_obs = np.asarray(t_obs, dtype=float)
    y_obs = np.asarray(y_obs, dtype=float)

    # Remove NaN pairs and sort by time
    mask = np.isfinite(t_obs) & np.isfinite(y_obs)
    t_obs, y_obs = t_obs[mask], y_obs[mask]
    order  = np.argsort(t_obs)
    t_obs, y_obs = t_obs[order], y_obs[order]

    t_max = float(t_obs.max()) if len(t_obs) > 0 else 100.0

    process_class = _classify_trajectory(t_obs, y_obs)
    results: dict[str, Any] = {}

    for model_name, cfg in KINETIC_MODELS.items():
        model_process = cfg["process"]

        # Skip models whose biological process doesn't match this trajectory
        if process_class in ("growth", "inactivation") and model_process != process_class:
            results[model_name] = {
                "converged": False,
                "skipped":   True,
                "reason": (
                    f"Trajectory classified as {process_class}; "
                    f"this model is for {model_process} — skipped."
                ),
            }
            continue

        if process_class in ("stable", "insufficient"):
            results[model_name] = {
                "converged": False,
                "skipped":   True,
                "reason": f"Trajectory is {process_class} (Δlog < 0.5); no model fitted.",
            }
            continue

        n = len(t_obs)
        if n < cfg["min_points"]:
            results[model_name] = {
                "converged": False,
                "reason": f"Too few observations ({n} < {cfg['min_points']} required for {model_name})",
            }
            continue

        func   = cfg["func"]
        p0     = cfg["p0_guess"](t_obs, y_obs)
        bounds = cfg["bounds_fn"](t_obs, y_obs)

        try:
            popt, pcov = curve_fit(
                func, t_obs, y_obs, p0=p0, bounds=bounds,
                maxfev=15000, method="trf",
            )
            y_pred  = func(t_obs, *popt)
            metrics = _compute_metrics(y_obs, y_pred, n_params=len(popt))
            perr    = np.sqrt(np.diag(pcov)) if pcov is not None else [None] * len(popt)

            violations = []
            if model_name == "baranyi":
                if popt[1] < popt[0]: violations.append("Nmax < N0")
                if popt[2] <= 0:      violations.append("mumax <= 0")
                if popt[3] < 0:       violations.append("lag < 0")
            elif model_name == "gompertz":
                if popt[1] <= 0:      violations.append("A <= 0")
                if popt[2] <= 0:      violations.append("mumax <= 0")
            elif model_name == "weibull_inact":
                if popt[1] <= 0:      violations.append("delta <= 0")
                if popt[2] <= 0:      violations.append("p <= 0")
            elif model_name == "geeraerd":
                if popt[2] <= 0:      violations.append("kmax <= 0")

            tf      = None
            tf_boot = None
            if threshold is not None:
                tf = _estimate_t_failure(func, list(popt), threshold, t_max, model_process)
                if tf is not None:
                    tf_boot = _bootstrap_t_failure(
                        t_obs, y_obs, func, popt, bounds, threshold, t_max, model_process
                    )

            loo = _loo_error(t_obs, y_obs, func, popt, bounds)

            result: dict[str, Any] = {
                "converged": True,
                "parameters": {
                    name: {
                        "value": float(v),
                        "se": float(e) if e is not None and np.isfinite(e) else None,
                    }
                    for name, v, e in zip(cfg["param_names"], popt, perr)
                },
                "metrics":    metrics,
                "violations": violations,
                "n_points":   int(n),
            }
            if loo:
                result["metrics"].update(loo)
            if tf is not None:
                result["t_failure"] = tf
            if tf_boot:
                result.update(tf_boot)

            # Dense prediction curve (100 points)
            t_pred       = np.linspace(0, max(t_max * 1.2, 1.0), 100)
            y_pred_curve = func(t_pred, *popt)
            result["curve"] = {
                "t":     t_pred.tolist(),
                "y":     y_pred_curve.tolist(),
                "y_obs": y_obs.tolist(),
                "t_obs": t_obs.tolist(),
            }

            results[model_name] = result

        except Exception as exc:
            results[model_name] = {"converged": False, "reason": str(exc)}

    return {
        "trajectory_id":  trajectory_id,
        "n_obs":          int(len(t_obs)),
        "process_class":  process_class,
        "models":         results,
    }


# ─── Public entry point ───────────────────────────────────────────────────────

def run_kinetic_training(
    df_records: list[dict],
    mapping: dict[str, str],
    threshold: float | None = None,
) -> dict[str, Any]:
    """
    Fit kinetic models to all trajectories in the dataset.

    Each trajectory is first classified as growth/inactivation/stable; only
    biologically appropriate models are then fitted.

    Args:
        df_records: list of row dicts (the uploaded dataset)
        mapping:    {column_name: role_id}
        threshold:  log₁₀(CFU/g) safety threshold for t_failure calculation

    Returns dict with:
        trajectories: per-trajectory results including process_class
        summary:      aggregate metrics per model
        counts:       classification summary
    """
    import pandas as pd

    role_to_col: dict[str, str] = {
        v: k for k, v in mapping.items() if v not in ("ignore", "unassigned")
    }

    required = {"trajectory_id", "time", "response"}
    missing  = required - set(role_to_col.keys())
    if missing:
        # Raised, not returned: an unmapped column is a user error the API must report as
        # a 422 naming the missing roles, not a dict the caller may forget to inspect.
        raise ValidationError(
            "The column mapping is missing roles this model family requires",
            details={"missing_roles": sorted(missing), "mapped_roles": sorted(role_to_col)},
        )

    df = pd.DataFrame(df_records)
    traj_col = role_to_col["trajectory_id"]
    time_col = role_to_col["time"]
    resp_col = role_to_col["response"]
    thr_col  = role_to_col.get("failure_threshold")

    df[time_col] = pd.to_numeric(df[time_col], errors="coerce")
    df[resp_col] = pd.to_numeric(df[resp_col], errors="coerce")
    df = df.dropna(subset=[time_col, resp_col])

    trajectory_results = []
    model_metrics: dict[str, dict[str, list]] = {
        m: {"rmse": [], "mae": [], "r2": []} for m in KINETIC_MODELS
    }

    class_counts: dict[str, int] = {
        "growth": 0, "inactivation": 0, "stable": 0, "insufficient": 0
    }

    for traj_id, grp in df.groupby(traj_col):
        t_obs = grp[time_col].values
        y_obs = grp[resp_col].values

        thr = threshold
        if thr is None and thr_col and thr_col in grp.columns:
            thr_vals = pd.to_numeric(grp[thr_col], errors="coerce").dropna()
            if len(thr_vals):
                thr = float(thr_vals.iloc[0])

        res = fit_trajectory(t_obs, y_obs, str(traj_id), threshold=thr)
        trajectory_results.append(res)

        pc = res.get("process_class", "insufficient")
        class_counts[pc] = class_counts.get(pc, 0) + 1

        for model_name in KINETIC_MODELS:
            m   = res["models"].get(model_name, {})
            met = m.get("metrics", {})
            if m.get("converged") and met.get("rmse") is not None:
                model_metrics[model_name]["rmse"].append(met["rmse"])
                if met.get("mae") is not None:
                    model_metrics[model_name]["mae"].append(met["mae"])
                if met.get("r2") is not None:
                    model_metrics[model_name]["r2"].append(met["r2"])

    summary: dict[str, Any] = {}
    for model_name, met_lists in model_metrics.items():
        rmses = met_lists["rmse"]
        if rmses:
            summary[model_name] = {
                "n_converged":  len(rmses),
                "mean_mae":     float(np.mean(met_lists["mae"])) if met_lists["mae"] else None,
                "mean_rmse":    float(np.mean(rmses)),
                "median_rmse":  float(np.median(rmses)),
                "mean_r2":      float(np.mean(met_lists["r2"])) if met_lists["r2"] else None,
            }
        else:
            summary[model_name] = {"n_converged": 0}

    n_conv   = {m: s["n_converged"] for m, s in summary.items()}
    best_model = max(n_conv, key=lambda m: n_conv[m]) if any(n_conv.values()) else None

    return {
        "n_trajectories": len(trajectory_results),
        "n_fitted": sum(
            1 for r in trajectory_results
            if any(r["models"].get(m, {}).get("converged") for m in KINETIC_MODELS)
        ),
        "trajectory_counts": class_counts,
        "best_model": best_model,
        "summary":    summary,
        "trajectories": trajectory_results,
    }
