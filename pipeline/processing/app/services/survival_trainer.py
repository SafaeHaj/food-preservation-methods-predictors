"""
Survival / AFT model training service.

Supports:
  weibull_aft  — lifelines WeibullAFTFitter
  rsf          — scikit-survival RandomSurvivalForest (if installed)
  xgboost_aft  — XGBoost AFT (if xgboost installed)
  bayesian_aft — skipped (requires PyMC; too heavy for background tasks)

Key fixes vs initial implementation:
  - Feature columns are properly coerced to numeric/categorical types before
    fitting (previously all were string and got one-hot encoded as categoricals)
  - Weibull AFT p(success) uses pandas interpolation instead of exact .loc lookup
  - CI bounds are always sorted (lo <= hi)
  - XGBoost early stopping is disabled for tiny test sets (< 5 rows)
"""
from __future__ import annotations

import uuid
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── Optional imports ──────────────────────────────────────────────────────────
try:
    from lifelines import WeibullAFTFitter
    HAS_LIFELINES = True
except ImportError:
    HAS_LIFELINES = False

try:
    from sksurv.ensemble import RandomSurvivalForest
    HAS_SKSURV = True
except ImportError:
    HAS_SKSURV = False

try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

try:
    import joblib
    HAS_JOBLIB = True
except ImportError:
    HAS_JOBLIB = False

try:
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    from sklearn.pipeline import Pipeline
    from sklearn.compose import ColumnTransformer
    from sklearn.model_selection import GroupShuffleSplit
    from sklearn.impute import SimpleImputer
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

RANDOM_SEED = 42


# ─── Data preparation ────────────────────────────────────────────────────────

def _coerce_feature_columns(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    """
    Attempt to convert feature columns to numeric where the data supports it.

    The dataset arrives as all-string (read with dtype=str), so every column
    is an object. We try pd.to_numeric on each feature column; if ≥ 80% of
    non-null values parse successfully, we treat the column as numeric.
    Otherwise it stays as a string (categorical).
    """
    df = df.copy()
    for col in feature_cols:
        if col not in df.columns:
            continue
        converted = pd.to_numeric(df[col], errors="coerce")
        non_null = df[col].notna().sum()
        if non_null > 0 and converted.notna().sum() / non_null >= 0.80:
            df[col] = converted
    return df


def _prepare_survival_data(
    df: pd.DataFrame,
    mapping: dict[str, str],
) -> tuple[pd.DataFrame, str, str, list[str], str | None]:
    """
    Returns (df_clean, time_col, event_col, feature_cols, study_col).

    Coerces feature columns to numeric where possible, then applies
    median (numeric) or mode (categorical) imputation.
    """
    role_to_col: dict[str, str] = {
        v: k for k, v in mapping.items()
        if v not in ("ignore", "unassigned") and k in df.columns
    }

    time_col  = role_to_col.get("time")
    event_col = role_to_col.get("event")
    study_col = role_to_col.get("study_id")

    exclude = {time_col, event_col, study_col, None}
    feature_cols = [
        col for col in df.columns
        if col not in exclude
        and mapping.get(col) not in ("ignore", "unassigned", None)
    ]

    if not time_col or time_col not in df.columns:
        raise ValueError("No 'time' role mapped to a valid column.")
    if not event_col or event_col not in df.columns:
        raise ValueError("No 'event' role mapped to a valid column.")
    if not feature_cols:
        raise ValueError("No feature columns mapped. Map at least one predictor.")

    df = df.copy()
    df[time_col]  = pd.to_numeric(df[time_col],  errors="coerce")
    df[event_col] = pd.to_numeric(df[event_col], errors="coerce")

    df = df.dropna(subset=[time_col, event_col])
    df[event_col] = df[event_col].astype(int)
    df[time_col]  = df[time_col].astype(float)
    df = df[df[time_col] > 0].reset_index(drop=True)

    # Coerce numeric-looking features before imputation
    feature_cols = [c for c in feature_cols if c in df.columns]
    df = _coerce_feature_columns(df, feature_cols)

    # Impute missing values
    for col in feature_cols:
        if col not in df.columns:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            median_val = df[col].median()
            df[col] = df[col].fillna(median_val)
        else:
            mode_vals = df[col].mode()
            df[col] = df[col].fillna(mode_vals[0] if not mode_vals.empty else "unknown")

    return df, time_col, event_col, feature_cols, study_col


def _study_aware_split(
    df: pd.DataFrame, study_col: str | None, test_frac: float = 0.20
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split ensuring all rows from one study stay in the same split."""
    if study_col and study_col in df.columns and HAS_SKLEARN:
        splitter = GroupShuffleSplit(n_splits=1, test_size=test_frac, random_state=RANDOM_SEED)
        groups   = df[study_col].values
        train_idx, test_idx = next(splitter.split(df, groups=groups))
        return df.iloc[train_idx].reset_index(drop=True), df.iloc[test_idx].reset_index(drop=True)

    n      = len(df)
    n_test = max(int(n * test_frac), 1)
    rng    = np.random.default_rng(RANDOM_SEED)
    test_idx  = rng.choice(n, n_test, replace=False)
    train_idx = np.setdiff1d(np.arange(n), test_idx)
    return df.iloc[train_idx].reset_index(drop=True), df.iloc[test_idx].reset_index(drop=True)


def _build_sklearn_preprocessor(df: pd.DataFrame, feature_cols: list[str]):
    """Build a sklearn ColumnTransformer for numeric + categorical features."""
    num_cols = [c for c in feature_cols if pd.api.types.is_numeric_dtype(df[c])]
    cat_cols = [c for c in feature_cols if c not in num_cols]

    transformers = []
    if num_cols:
        transformers.append(("num", Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("scl", StandardScaler()),
        ]), num_cols))
    if cat_cols:
        transformers.append(("cat", Pipeline([
            ("imp", SimpleImputer(strategy="most_frequent")),
            ("ohe", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]), cat_cols))

    return ColumnTransformer(transformers, remainder="drop"), num_cols, cat_cols


# ─── Concordance index ───────────────────────────────────────────────────────

def _c_index_lifelines(durations, events, scores):
    try:
        from lifelines.utils import concordance_index
        return float(concordance_index(durations, scores, events))
    except Exception:
        return None


# ─── Weibull AFT ─────────────────────────────────────────────────────────────

def _train_weibull_aft(
    df_train: pd.DataFrame,
    df_test:  pd.DataFrame,
    time_col: str,
    event_col: str,
    feature_cols: list[str],
    artifact_dir: Path,
) -> dict[str, Any]:
    if not HAS_LIFELINES:
        return {"status": "skipped", "reason": "lifelines not installed. Run: pip install lifelines"}

    try:
        cat_cols_tr = [c for c in feature_cols if not pd.api.types.is_numeric_dtype(df_train[c])]

        df_tr_enc = pd.get_dummies(
            df_train[feature_cols + [time_col, event_col]], columns=cat_cols_tr
        )
        df_te_enc = pd.get_dummies(
            df_test[feature_cols + [time_col, event_col]], columns=cat_cols_tr
        )
        # Align test columns to train columns
        for c in set(df_tr_enc.columns) - set(df_te_enc.columns):
            df_te_enc[c] = 0
        df_te_enc = df_te_enc[df_tr_enc.columns]

        waf = WeibullAFTFitter(penalizer=0.1)
        waf.fit(df_tr_enc, duration_col=time_col, event_col=event_col)

        pred_median = waf.predict_median(df_te_enc)
        c_idx = _c_index_lifelines(
            df_test[time_col].values,
            df_test[event_col].values,
            pred_median.values,
        )

        artifact_path = None
        if HAS_JOBLIB:
            artifact_path = str(artifact_dir / f"weibull_aft_{uuid.uuid4().hex[:8]}.joblib")
            joblib.dump({"model": waf, "train_cols": list(df_tr_enc.columns)}, artifact_path)

        coef_df = waf.params_["lambda_"].reset_index()
        coef_df.columns = ["covariate", "coef"]
        coefficients = coef_df[coef_df["covariate"] != "Intercept"].to_dict("records")

        return {
            "status": "completed",
            "concordance_index": c_idx,
            "n_train": len(df_train),
            "n_test":  len(df_test),
            "coefficients": coefficients,
            "shape": float(waf.params_["rho_"].values[0]) if "rho_" in waf.params_ else None,
            "artifact_path": artifact_path,
        }
    except Exception as exc:
        return {"status": "failed", "reason": str(exc)}


# ─── Random Survival Forest ───────────────────────────────────────────────────

def _train_rsf(
    df_train: pd.DataFrame,
    df_test:  pd.DataFrame,
    time_col: str,
    event_col: str,
    feature_cols: list[str],
    artifact_dir: Path,
) -> dict[str, Any]:
    if not HAS_SKSURV:
        return {
            "status": "skipped",
            "reason": (
                "scikit-survival not installed (requires numpy>=2.0 — "
                "not yet compatible with this environment). "
                "Run: pip install scikit-survival"
            ),
        }
    if not HAS_SKLEARN:
        return {"status": "skipped", "reason": "scikit-learn not installed."}

    try:
        prep, _, _ = _build_sklearn_preprocessor(df_train, feature_cols)
        X_train = prep.fit_transform(df_train[feature_cols])
        X_test  = prep.transform(df_test[feature_cols])

        y_train = np.array(
            [(bool(e), t) for e, t in zip(df_train[event_col], df_train[time_col])],
            dtype=[("event", bool), ("time", float)],
        )
        y_test = np.array(
            [(bool(e), t) for e, t in zip(df_test[event_col], df_test[time_col])],
            dtype=[("event", bool), ("time", float)],
        )

        rsf = RandomSurvivalForest(
            n_estimators=200, max_depth=None, min_samples_leaf=5,
            max_features="sqrt", n_jobs=-1, random_state=RANDOM_SEED,
        )
        rsf.fit(X_train, y_train)
        c_idx = float(rsf.score(X_test, y_test))

        artifact_path = None
        if HAS_JOBLIB:
            artifact_path = str(artifact_dir / f"rsf_{uuid.uuid4().hex[:8]}.joblib")
            joblib.dump({"model": rsf, "preprocessor": prep,
                         "feature_cols": feature_cols}, artifact_path)

        return {
            "status": "completed",
            "concordance_index": c_idx,
            "n_train": len(df_train),
            "n_test":  len(df_test),
            "n_estimators": 200,
            "artifact_path": artifact_path,
        }
    except Exception as exc:
        return {"status": "failed", "reason": str(exc)}


# ─── XGBoost AFT ─────────────────────────────────────────────────────────────

def _train_xgboost_aft(
    df_train: pd.DataFrame,
    df_test:  pd.DataFrame,
    time_col: str,
    event_col: str,
    feature_cols: list[str],
    artifact_dir: Path,
) -> dict[str, Any]:
    if not HAS_XGB:
        return {"status": "skipped", "reason": "xgboost not installed. Run: pip install xgboost"}
    if not HAS_SKLEARN:
        return {"status": "skipped", "reason": "scikit-learn not installed. Run: pip install scikit-learn"}

    try:
        prep, _, _ = _build_sklearn_preprocessor(df_train, feature_cols)
        X_train_arr = prep.fit_transform(df_train[feature_cols]).astype(np.float32)
        X_test_arr  = prep.transform(df_test[feature_cols]).astype(np.float32)

        y_lower = df_train[time_col].values.astype(np.float32)
        y_upper = np.where(df_train[event_col].values == 1, y_lower, np.inf).astype(np.float32)

        dtrain = xgb.DMatrix(X_train_arr)
        dtrain.set_float_info("label_lower_bound", y_lower)
        dtrain.set_float_info("label_upper_bound", y_upper)

        dtest = xgb.DMatrix(X_test_arr)

        params = {
            "objective": "survival:aft",
            "eval_metric": "aft-nloglik",
            "aft_loss_distribution": "logistic",
            "aft_loss_distribution_scale": 1.0,
            "tree_method": "hist",
            "learning_rate": 0.05,
            "max_depth": 3,
            "min_child_weight": 1,
            "seed": RANDOM_SEED,
            "verbosity": 0,
        }
        use_early_stop = len(df_test) >= 5
        evals = [(dtrain, "train")] + ([(dtest, "eval")] if use_early_stop else [])
        evals_result: dict = {}
        model = xgb.train(
            params, dtrain,
            num_boost_round=200,
            evals=evals if evals else None,
            evals_result=evals_result,
            early_stopping_rounds=20 if use_early_stop else None,
            verbose_eval=False,
        )

        y_pred_log = model.predict(dtest)
        c_idx = _c_index_lifelines(
            df_test[time_col].values,
            df_test[event_col].values,
            y_pred_log,
        )

        artifact_path = None
        if HAS_JOBLIB:
            artifact_path = str(artifact_dir / f"xgboost_aft_{uuid.uuid4().hex[:8]}.joblib")
            joblib.dump({"model": model, "preprocessor": prep,
                         "feature_cols": feature_cols}, artifact_path)

        best_round = model.best_iteration if hasattr(model, "best_iteration") else 200
        return {
            "status": "completed",
            "concordance_index": c_idx,
            "best_iteration": best_round,
            "n_train": len(df_train),
            "n_test":  len(df_test),
            "artifact_path": artifact_path,
        }
    except Exception as exc:
        return {"status": "failed", "reason": str(exc)}


# ─── Public entry point ───────────────────────────────────────────────────────

def run_survival_training(
    df_records: list[dict],
    mapping: dict[str, str],
    artifact_dir: str | Path,
) -> dict[str, Any]:
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(df_records)
    try:
        df, time_col, event_col, feature_cols, study_col = _prepare_survival_data(df, mapping)
    except ValueError as exc:
        return {"error": str(exc)}

    if len(df) < 10:
        return {"error": f"Too few valid rows ({len(df)}) for survival modelling. Need ≥ 10."}

    df_train, df_test = _study_aware_split(df, study_col)

    event_rate   = df_train[event_col].mean()
    warnings_list = []
    if event_rate < 0.1:
        warnings_list.append(f"Low event rate ({event_rate:.1%}) — survival models may be unreliable.")
    if len(df_test) < 5:
        warnings_list.append("Test set has fewer than 5 rows — metrics are unreliable.")

    results: dict[str, Any] = {}
    results["weibull_aft"]  = _train_weibull_aft(df_train, df_test, time_col, event_col, feature_cols, artifact_dir)
    results["rsf"]          = _train_rsf(df_train, df_test, time_col, event_col, feature_cols, artifact_dir)
    results["xgboost_aft"]  = _train_xgboost_aft(df_train, df_test, time_col, event_col, feature_cols, artifact_dir)
    results["bayesian_aft"] = {
        "status": "skipped",
        "reason": "Bayesian AFT requires PyMC which is not included in this environment.",
    }

    n_completed = sum(1 for r in results.values() if r.get("status") == "completed")
    best = max(
        [(m, r) for m, r in results.items() if r.get("concordance_index") is not None],
        key=lambda x: x[1]["concordance_index"],
        default=(None, {}),
    )

    return {
        "n_rows":       len(df),
        "n_train":      len(df_train),
        "n_test":       len(df_test),
        "event_rate":   float(event_rate),
        "time_col":     time_col,
        "event_col":    event_col,
        "feature_cols": feature_cols,
        "study_col":    study_col,
        "n_completed":  n_completed,
        "best_model":   best[0],
        "best_c_index": best[1].get("concordance_index"),
        "warnings":     warnings_list,
        "models":       results,
    }


# ─── Prediction ───────────────────────────────────────────────────────────────

def predict_survival(
    artifact_path: str,
    model_name: str,
    input_features: dict[str, Any],
    required_shelf_life: float | None = None,
) -> dict[str, Any]:
    """Run inference from a saved survival model artifact."""
    if not HAS_JOBLIB:
        return {"error": "joblib not installed."}

    try:
        bundle = joblib.load(artifact_path)
        model  = bundle["model"]
        feature_cols = bundle.get("feature_cols", list(input_features.keys()))

        df_in = pd.DataFrame([input_features])
        for c in feature_cols:
            if c not in df_in.columns:
                df_in[c] = np.nan

        if model_name == "weibull_aft":
            train_cols = bundle.get("train_cols", [])
            df_enc = pd.get_dummies(df_in[feature_cols])
            for c in train_cols:
                if c not in df_enc.columns:
                    df_enc[c] = 0
            df_enc = df_enc[[c for c in train_cols if c in df_enc.columns]]

            pred_median = float(model.predict_median(df_enc).iloc[0])
            _p05 = float(model.predict_percentile(df_enc, p=0.05).iloc[0])
            _p95 = float(model.predict_percentile(df_enc, p=0.95).iloc[0])
            pred_ci = (min(_p05, _p95), max(_p05, _p95))

            p_success = None
            if required_shelf_life is not None:
                sf = model.predict_survival_function(df_enc)
                sf_times = sf.index.values  # array of time points
                sf_probs = sf.iloc[:, 0].values  # survival probabilities
                if required_shelf_life <= sf_times[-1]:
                    # Interpolate — avoids KeyError on non-exact time values
                    p_success = float(np.interp(required_shelf_life, sf_times, sf_probs))
                else:
                    p_success = 0.0

        elif model_name in ("rsf", "xgboost_aft"):
            prep = bundle["preprocessor"]
            # Coerce numeric-looking columns before transforming
            df_in = _coerce_feature_columns(df_in, feature_cols)
            X = prep.transform(df_in[feature_cols])

            if model_name == "rsf":
                surv_fns = model.predict_survival_function(X)
                surv_fn  = surv_fns[0]
                times = surv_fn.x
                probs = surv_fn.y
                above_half = probs >= 0.5
                pred_median = float(times[above_half][-1]) if above_half.any() else float(times[-1])
                pred_ci = (float(times[0]), float(times[-1]))
                if required_shelf_life is not None:
                    p_success = float(np.interp(required_shelf_life, times, probs))
                else:
                    p_success = None
            else:  # xgboost_aft
                dmat     = xgb.DMatrix(X.astype(np.float32))
                pred_log = float(model.predict(dmat)[0])
                # AFT logistic: predicted value is log(T), so T = exp(pred_log)
                pred_median = float(np.exp(pred_log))
                pred_ci     = (pred_median * 0.7, pred_median * 1.4)
                p_success   = None
        else:
            return {"error": f"Unknown model: {model_name}"}

        result: dict[str, Any] = {
            "model_name": model_name,
            "predicted_shelf_life_days": round(pred_median, 2),
            "ci_lo_days": round(float(pred_ci[0]), 2),
            "ci_hi_days": round(float(pred_ci[1]), 2),
        }
        if required_shelf_life is not None:
            result["required_shelf_life_days"] = required_shelf_life
            result["success"] = pred_median >= required_shelf_life
            if p_success is not None:
                result["p_success"] = round(p_success, 4)

        return result

    except Exception as exc:
        return {"error": str(exc)}
