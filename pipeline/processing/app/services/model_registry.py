"""
Scientific model registry.

Growth models: Gompertz (modified), Baranyi-Roberts, Logistic, Richards
Inactivation models: Log-linear, Weibull, Geeraerd, Biphasic

Each model exposes:
  - equation(t, **params) → float
  - bounds() → dict of (lower, upper) per param
  - initial_guess(t_obs, y_obs) → dict of initial param values
  - param_names: list[str]
  - process_class: "growth" | "inactivation"
  - biological_constraints(params) → list[str]  (violation messages)
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ════════════════════════════════════════════════════════════════════════════
# GROWTH MODELS
# ════════════════════════════════════════════════════════════════════════════

def _gompertz(t: np.ndarray, N0: float, Nmax: float, mu_max: float, lambda_: float) -> np.ndarray:
    """Modified Gompertz (Zwietering 1990)."""
    exp_part = np.exp(
        np.exp(mu_max * math.e / (Nmax - N0) * (lambda_ - t) + 1)
    )
    return N0 + (Nmax - N0) * np.exp(-exp_part)


def _baranyi(t: np.ndarray, N0: float, Nmax: float, mu_max: float, h0: float) -> np.ndarray:
    """Simplified Baranyi-Roberts."""
    A = t + (1 / mu_max) * np.log(np.exp(-mu_max * t) + np.exp(-h0) - np.exp(-mu_max * t - h0))
    return Nmax - np.log1p(np.expm1(Nmax - N0) * np.exp(-mu_max * A))


def _logistic(t: np.ndarray, N0: float, Nmax: float, mu_max: float) -> np.ndarray:
    """Logistic / Verhulst."""
    return Nmax / (1 + ((Nmax - N0) / N0) * np.exp(-mu_max * t))


def _richards(t: np.ndarray, N0: float, Nmax: float, mu_max: float, nu: float) -> np.ndarray:
    """Richards generalised growth."""
    m = (Nmax / N0) ** nu
    return Nmax / (1 + (m - 1) * np.exp(-mu_max * nu * t)) ** (1 / nu)


# ════════════════════════════════════════════════════════════════════════════
# INACTIVATION MODELS
# ════════════════════════════════════════════════════════════════════════════

def _log_linear(t: np.ndarray, N0: float, k: float) -> np.ndarray:
    """First-order log-linear inactivation."""
    return N0 - k * t


def _weibull(t: np.ndarray, N0: float, b: float, n: float) -> np.ndarray:
    """Weibull inactivation (Mafart 2002)."""
    return N0 - b * (t ** n)


def _geeraerd(t: np.ndarray, N0: float, Nres: float, kmax: float, Si: float) -> np.ndarray:
    """Geeraerd with shoulder and tail."""
    return (
        (N0 - Nres) * np.exp(-kmax * t) * (1 / (1 + (np.exp(kmax * Si) - 1) * np.exp(-kmax * t)))
        + Nres
    )


def _biphasic(t: np.ndarray, N0: float, f: float, k1: float, k2: float) -> np.ndarray:
    """Biphasic inactivation (two sub-populations)."""
    return np.log10(
        f * 10**N0 * np.exp(-k1 * t) + (1 - f) * 10**N0 * np.exp(-k2 * t)
    )


# ════════════════════════════════════════════════════════════════════════════
# MODEL METADATA
# ════════════════════════════════════════════════════════════════════════════

MODELS = {
    "Gompertz": {
        "func": _gompertz,
        "params": ["N0", "Nmax", "mu_max", "lambda_"],
        "process_class": "growth",
        "bounds": {"N0": (0, 15), "Nmax": (0, 15), "mu_max": (0, 10), "lambda_": (0, 100)},
        "equation": "N0 + (Nmax-N0)*exp(-exp(mu_max*e/(Nmax-N0)*(lambda-t)+1))",
    },
    "Baranyi": {
        "func": _baranyi,
        "params": ["N0", "Nmax", "mu_max", "h0"],
        "process_class": "growth",
        "bounds": {"N0": (0, 15), "Nmax": (0, 15), "mu_max": (0, 10), "h0": (0, 100)},
        "equation": "Baranyi-Roberts (1994) simplified",
    },
    "Logistic": {
        "func": _logistic,
        "params": ["N0", "Nmax", "mu_max"],
        "process_class": "growth",
        "bounds": {"N0": (0, 15), "Nmax": (0, 15), "mu_max": (0, 10)},
        "equation": "Nmax / (1 + ((Nmax-N0)/N0)*exp(-mu_max*t))",
    },
    "Richards": {
        "func": _richards,
        "params": ["N0", "Nmax", "mu_max", "nu"],
        "process_class": "growth",
        "bounds": {"N0": (0, 15), "Nmax": (0, 15), "mu_max": (0, 10), "nu": (0.01, 10)},
        "equation": "Richards generalised (nu=1 → logistic)",
    },
    "LogLinear": {
        "func": _log_linear,
        "params": ["N0", "k"],
        "process_class": "inactivation",
        "bounds": {"N0": (0, 15), "k": (0, 100)},
        "equation": "N0 - k*t",
    },
    "Weibull": {
        "func": _weibull,
        "params": ["N0", "b", "n"],
        "process_class": "inactivation",
        "bounds": {"N0": (0, 15), "b": (0, 100), "n": (0.01, 10)},
        "equation": "N0 - b*t^n",
    },
    "Geeraerd": {
        "func": _geeraerd,
        "params": ["N0", "Nres", "kmax", "Si"],
        "process_class": "inactivation",
        "bounds": {"N0": (0, 15), "Nres": (0, 15), "kmax": (0, 100), "Si": (0, 100)},
        "equation": "Geeraerd (2000) with shoulder and tail",
    },
    "Biphasic": {
        "func": _biphasic,
        "params": ["N0", "f", "k1", "k2"],
        "process_class": "inactivation",
        "bounds": {"N0": (0, 15), "f": (0.01, 0.99), "k1": (0, 100), "k2": (0, 100)},
        "equation": "log10(f*10^N0*exp(-k1*t) + (1-f)*10^N0*exp(-k2*t))",
    },
}


def _initial_guess(model_name: str, t_obs: np.ndarray, y_obs: np.ndarray) -> dict:
    N0_est = float(y_obs[t_obs == t_obs.min()].mean()) if len(y_obs) else 1.0
    Nmax_est = float(y_obs.max())
    mu_est = max(0.01, (Nmax_est - N0_est) / (t_obs.max() - t_obs.min() + 1e-9))

    guesses = {
        "Gompertz":  {"N0": N0_est, "Nmax": Nmax_est, "mu_max": mu_est, "lambda_": 1.0},
        "Baranyi":   {"N0": N0_est, "Nmax": Nmax_est, "mu_max": mu_est, "h0": 4.0},
        "Logistic":  {"N0": N0_est, "Nmax": Nmax_est, "mu_max": mu_est},
        "Richards":  {"N0": N0_est, "Nmax": Nmax_est, "mu_max": mu_est, "nu": 1.0},
        "LogLinear": {"N0": N0_est, "k": max(0.01, (N0_est - y_obs.min()) / (t_obs.max() + 1e-9))},
        "Weibull":   {"N0": N0_est, "b": 0.1, "n": 1.0},
        "Geeraerd":  {"N0": N0_est, "Nres": max(0, y_obs.min()), "kmax": 0.5, "Si": 2.0},
        "Biphasic":  {"N0": N0_est, "f": 0.9, "k1": 1.0, "k2": 0.1},
    }
    return guesses.get(model_name, {})


def _biological_violations(model_name: str, params: dict) -> list[str]:
    violations = []
    if "N0" in params and "Nmax" in params:
        if params["Nmax"] <= params["N0"] and model_name in ("Gompertz", "Baranyi", "Logistic", "Richards"):
            violations.append("Nmax must be > N0 for growth models")
    if "mu_max" in params and params.get("mu_max", 0) < 0:
        violations.append("mu_max must be non-negative")
    if "k" in params and params.get("k", 0) < 0:
        violations.append("inactivation rate k must be non-negative")
    if model_name == "Biphasic":
        if not (0 < params.get("f", 0.5) < 1):
            violations.append("f must be between 0 and 1 (sub-population fraction)")
        if params.get("k1", 0) < params.get("k2", 0):
            violations.append("k1 should be >= k2 (sensitive sub-population should die faster)")
    return violations


# ════════════════════════════════════════════════════════════════════════════
# FITTING ENGINE
# ════════════════════════════════════════════════════════════════════════════

def _fit_one_model(model_name: str, t: np.ndarray, y: np.ndarray) -> dict:
    from scipy.optimize import curve_fit
    from scipy.stats import pearsonr

    meta = MODELS[model_name]
    func = meta["func"]
    param_names = meta["params"]
    bounds_dict = meta["bounds"]

    p0_dict = _initial_guess(model_name, t, y)
    p0 = [p0_dict.get(p, 1.0) for p in param_names]
    lower = [bounds_dict.get(p, (-np.inf, np.inf))[0] for p in param_names]
    upper = [bounds_dict.get(p, (-np.inf, np.inf))[1] for p in param_names]

    try:
        popt, pcov = curve_fit(func, t, y, p0=p0, bounds=(lower, upper),
                               maxfev=10000, method="trf")
        perr = np.sqrt(np.diag(pcov))
        y_pred = func(t, *popt)
        residuals = y - y_pred
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        n = len(y)
        k = len(param_names)
        r2 = 1 - ss_res / (ss_tot + 1e-12)
        adj_r2 = 1 - (1 - r2) * (n - 1) / max(n - k - 1, 1)
        rmse = float(np.sqrt(ss_res / n))
        mae = float(np.mean(np.abs(residuals)))
        # AIC / BIC
        sigma2 = ss_res / n
        log_likelihood = -n / 2 * np.log(2 * np.pi * sigma2) - ss_res / (2 * sigma2)
        aic = 2 * k - 2 * log_likelihood
        bic = k * np.log(n) - 2 * log_likelihood
        aicc = aic + 2 * k * (k + 1) / max(n - k - 1, 1)
        # LOO-CV (only if n > k+1)
        loo_errors = []
        if n > k + 1:
            for i in range(n):
                t_loo = np.delete(t, i)
                y_loo = np.delete(y, i)
                try:
                    popt_loo, _ = curve_fit(func, t_loo, y_loo, p0=list(popt),
                                            bounds=(lower, upper), maxfev=5000)
                    loo_errors.append(abs(y[i] - func(np.array([t[i]]), *popt_loo)[0]))
                except Exception:
                    pass

        params_dict = dict(zip(param_names, [float(p) for p in popt]))
        se_dict = dict(zip(param_names, [float(e) for e in perr]))
        violations = _biological_violations(model_name, params_dict)
        return {
            "converged": True,
            "parameters": params_dict,
            "parameter_se": se_dict,
            "mae": mae,
            "rmse": rmse,
            "r_squared": float(r2),
            "adjusted_r_squared": float(adj_r2),
            "aic": float(aic),
            "bic": float(bic),
            "aicc": float(aicc),
            "residual_bias": float(np.mean(residuals)),
            "loo_mae": float(np.mean(loo_errors)) if loo_errors else None,
            "loo_rmse": float(np.sqrt(np.mean(np.array(loo_errors) ** 2))) if loo_errors else None,
            "biological_violations": len(violations),
            "applicability_reasons": violations,
            "equation_text": meta["equation"],
        }
    except Exception as exc:
        return {
            "converged": False,
            "convergence_message": str(exc),
            "parameters": {},
            "parameter_se": {},
        }


def _classify_process(y: np.ndarray) -> str:
    if len(y) < 2:
        return "insufficient_data"
    trend = np.polyfit(np.arange(len(y)), y, 1)[0]
    if trend > 0.01:
        return "growth"
    if trend < -0.01:
        return "inactivation"
    return "stable"


# ════════════════════════════════════════════════════════════════════════════
# ASYNC ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

def fit_trajectory_async(run_id: int) -> None:
    """Background task: fit all models for a trajectory ModelRun."""
    from shared.db.database import SessionLocal
    from shared.db.models import ModelFit, ModelPrediction, ModelRun, Observation, TrajectoryDefinition

    db: Session = SessionLocal()
    try:
        run = db.query(ModelRun).filter(ModelRun.id == run_id).first()
        if not run:
            return
        run.status = "running"
        db.commit()

        traj = db.query(TrajectoryDefinition).filter(
            TrajectoryDefinition.id == run.trajectory_id
        ).first()
        if not traj:
            run.status = "failed"
            run.error_message = "Trajectory not found"
            db.commit()
            return

        obs_ids = traj.observation_ids
        if not obs_ids:
            run.status = "failed"
            run.error_message = "No observations in trajectory"
            db.commit()
            return

        obs_list = (db.query(Observation)
                      .filter(Observation.id.in_(obs_ids))
                      .order_by(Observation.time_days)
                      .all())
        t_vals = np.array([o.time_days for o in obs_list if o.time_days is not None], dtype=float)
        y_vals = np.array([o.numeric_value_normalized for o in obs_list
                           if o.time_days is not None and o.numeric_value_normalized is not None],
                          dtype=float)

        if len(t_vals) < 3:
            run.status = "failed"
            run.error_message = "Fewer than 3 data points — cannot fit"
            db.commit()
            return

        process_class = _classify_process(y_vals)
        traj.process_class = process_class
        traj.data_sufficient = len(t_vals) >= 4
        db.commit()

        candidate_models = [
            name for name, meta in MODELS.items()
            if meta["process_class"] == process_class
        ]
        if not candidate_models:
            candidate_models = list(MODELS.keys())

        fits = []
        run.models_tried = len(candidate_models)
        for name in candidate_models:
            result = _fit_one_model(name, t_vals, y_vals)
            fit = ModelFit(
                run_id=run_id,
                model_name=name,
                process_class=process_class,
                converged=result.get("converged", False),
                convergence_message=result.get("convergence_message"),
                parameters_json=json.dumps(result.get("parameters", {})),
                parameter_se_json=json.dumps(result.get("parameter_se", {})),
                mae=result.get("mae"),
                rmse=result.get("rmse"),
                r_squared=result.get("r_squared"),
                adjusted_r_squared=result.get("adjusted_r_squared"),
                aic=result.get("aic"),
                bic=result.get("bic"),
                aicc=result.get("aicc"),
                residual_bias=result.get("residual_bias"),
                loo_mae=result.get("loo_mae"),
                loo_rmse=result.get("loo_rmse"),
                biological_violations=result.get("biological_violations", 0),
                applicability_reasons_json=json.dumps(result.get("applicability_reasons", [])),
                equation_text=result.get("equation_text"),
            )
            db.add(fit)
            db.flush()

            # Determine applicability
            violations = result.get("biological_violations", 0)
            r2 = result.get("r_squared", 0) or 0
            if not result.get("converged"):
                fit.applicability_status = "red"
            elif violations > 0 or r2 < 0.7:
                fit.applicability_status = "yellow"
            else:
                fit.applicability_status = "green"

            # Generate predictions
            t_pred = np.linspace(t_vals.min(), t_vals.max(), 50)
            if result.get("converged") and result.get("parameters"):
                params = result["parameters"]
                func = MODELS[name]["func"]
                param_names = MODELS[name]["params"]
                try:
                    y_pred = func(t_pred, *[params[p] for p in param_names])
                    for tp, yp in zip(t_pred, y_pred):
                        db.add(ModelPrediction(
                            fit_id=fit.id,
                            time_days=float(tp),
                            predicted_value=float(yp),
                        ))
                except Exception:
                    pass

            if result.get("converged"):
                fits.append(fit)

        # Rank converged fits by AICc
        converged = [f for f in fits if f.converged and f.aicc is not None]
        converged.sort(key=lambda f: (f.aicc or 1e9))
        for rank, fit in enumerate(converged, start=1):
            fit.rank = rank

        run.models_converged = len(converged)
        if converged:
            run.selected_model_id = converged[0].id
        run.status = "completed"
        run.completed_at = datetime.utcnow()
        db.commit()

    except Exception as exc:
        db.rollback()
        try:
            run = db.query(ModelRun).filter(ModelRun.id == run_id).first()
            if run:
                run.status = "failed"
                run.error_message = str(exc)
                run.completed_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
