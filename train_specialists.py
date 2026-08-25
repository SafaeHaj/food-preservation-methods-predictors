#!/usr/bin/env python
"""
Train the V6 specialist model families: one model set per
(cheese_category, model_task) combination --

    soft/general_shelf_life   soft/safety_endpoint
    semi_hard/general_shelf_life   semi_hard/safety_endpoint
    hard/general_shelf_life   hard/safety_endpoint

each trained on its own CSV (data/raw/CHEESE_SHELF_LIFE_V6_{CATEGORY}_SPECIALIST.csv),
filtered to its model_task, with the same RF/LightGBM/XGBoost/EBM ensemble
`train_models.py` uses for the legacy single-model app.

This script intentionally does NOT `import train_models` -- that module has
no `if __name__ == "__main__":` guard, so importing it would execute the
entire legacy training run (and clobber artifacts/) as a side effect. Its
~13 pure, side-effect-free helper functions are mirrored verbatim below
instead (marked where they start/end). `make_context_splits` and
`FrameImputer` are imported for real from model_service.py, which has no
top-level execution.

Usage:
    python train_specialists.py                      # train all 6
    python train_specialists.py --category soft       # just one category (both tasks)
    python train_specialists.py --category soft --task general_shelf_life  # just one model family
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Any

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    mean_absolute_error, mean_absolute_percentage_error, mean_squared_error,
    median_absolute_error, r2_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

warnings.filterwarnings("ignore")

SEED = 42
ROOT = Path(__file__).resolve().parent
TARGET = "shelf_life_days"
CATEGORIES = ["soft", "semi_hard", "hard"]
TASKS = ["general_shelf_life", "safety_endpoint"]

# make_context_splits/FrameImputer live in model_service.py, which has no
# top-level execution -- safe to import for real (unlike train_models.py).
from model_service import make_context_splits, FrameImputer, build_matrix_lookup, build_ingredient_lookup  # noqa: E402
from concentration_units import to_canonical  # noqa: E402

ID_COLUMNS = ["row_id", "context_id", "formulation_id", "source_rule_id"]
PROVENANCE_COLUMNS = ["data_origin", "training_weight", "quality_flag"]
# V6-specific excludes -- see plan doc for the verified rationale behind each:
#   cheese_category            constant within any one specialist file (== the routing key itself)
#   base_cheese_name           redundant with food_matrix (catalog-only, not a model feature)
#   physical_form_source/confidence   describe provenance of the physical_form LABEL, not a
#                               physical property -- feeding "how sure we are" back into the
#                               model would be a leakage-flavored nonsense feature
#   endpoint_role               perfect deterministic recoding of indicator_group (zero
#                               off-diagonal mass in the crosstab) -- pure redundancy
#   is_pathogen_indicator       literally constant within any single (category, task) split
#   canonical_indicator_unit    exact pass-through of indicator_unit -- pure duplication
#   split_group                 byte-identical to context_id
#   shelf_life_days_v4_original / target_recalibration_factor / target_recalibration_note   audit trail
#   model_task                  the file-split key itself
#   primary_concentration(_unit)   superseded by canonical_concentration_value/unit
V6_SPECIFIC_EXCLUDE = [
    "cheese_category", "base_cheese_name",
    "physical_form_source", "physical_form_confidence",
    "endpoint_role", "is_pathogen_indicator", "canonical_indicator_unit",
    "split_group",
    "shelf_life_days_v4_original", "target_recalibration_factor", "target_recalibration_note",
    "model_task",
    "primary_concentration", "primary_concentration_unit",
]
EXCLUDED_COLUMNS_V6 = ID_COLUMNS + PROVENANCE_COLUMNS + V6_SPECIFIC_EXCLUDE
GROUP_COLS_FOR_ANALYSIS = ["food_matrix", "indicator_type", "is_control", "physical_form"]

# V7 adds 13 columns beyond V6. Verified against the actual V7 CSVs (not
# assumed) before deciding feature vs exclude:
#   routing_category            perfectly 1:1 with cheese_category today (asserted at
#                                train time below) -- same exclusion rationale as cheese_category
#   physical_form_observed      constant 0 across every V7 row (no observed-vs-inferred
#                                signal exists yet) -- zero variance, not a physical property
#   endpoint_threshold_basis    perfectly bijective with model_task per file -- zero
#                                variance within any one specialist, same as model_task itself
#   is_challenge_test           also perfectly bijective with model_task per file -- zero
#                                variance within any one specialist
#   evidence_class               provenance (data_origin-like), not a physical property
#   observed_fields              single constant narrative string per file -- pure provenance
#   source_url / source_note     citation provenance, like source_rule_id
#   generation_rule_version      constant per file -- versioning metadata
#   matrix_profile_confidence    constant 0.86 per file -- zero variance, provenance-like
#   target_is_lower_bound        describes the TARGET's censoring semantics, not a live
#                                input a user could supply -- reported in the manifest
#                                instead (see pct_lower_bound_target_* below), never fed
#                                into the model or a correction
V7_EXTRA_EXCLUDE = [
    "routing_category", "physical_form_observed", "endpoint_threshold_basis", "is_challenge_test",
    "evidence_class", "observed_fields", "source_url", "source_note",
    "generation_rule_version", "matrix_profile_confidence", "target_is_lower_bound",
]
EXCLUDED_COLUMNS_V7 = EXCLUDED_COLUMNS_V6 + V7_EXTRA_EXCLUDE

# Genuine new safety-only features, deliberately NOT excluded above -- this is
# the extension point the V6-era comment anticipated ("if/when challenge-study
# data exists, add these and retrain"). Verified: initial_inoculum_log_cfu_g
# (220-226 distinct values per file) and growth_support (2-3 categories,
# correlates with but is not a deterministic recoding of any other included
# column) are 100% populated for safety_endpoint rows and 100% absent for
# general_shelf_life rows within each V7 file -- handled generically below by
# excluding, per specialist, any column that is 100% null in that specialist's
# own task-filtered training data (not hardcoded here as "safety-only").

DATA_VERSION_CONFIG: dict[str, dict[str, Any]] = {
    "v6": {
        "csv_pattern": "CHEESE_SHELF_LIFE_V6_{CAT}_SPECIALIST.csv",
        "artifacts_dir": "artifacts_v6",
        "exclude": EXCLUDED_COLUMNS_V6,
    },
    "v7": {
        "csv_pattern": "CHEESE_SHELF_LIFE_V7_{CAT}_SPECIALIST_CORRECTED.csv",
        "artifacts_dir": "artifacts_v7",
        "exclude": EXCLUDED_COLUMNS_V7,
    },
}


# ══════════════════════════════════════════════════════════════════════════
# Mirrored verbatim from train_models.py (not imported -- see module docstring)
# ══════════════════════════════════════════════════════════════════════════

def detect_schema(df: pd.DataFrame, target: str, exclude: list[str] = ()) -> dict[str, list[str]]:
    feature_cols = [c for c in df.columns if c != target and c not in exclude]
    numeric, categorical, binary = [], [], []
    for c in feature_cols:
        if df[c].dtype == object:
            categorical.append(c)
            continue
        uniques = set(pd.Series(df[c]).dropna().unique().tolist())
        if uniques.issubset({0, 1}) and len(uniques) <= 2:
            binary.append(c)
        else:
            numeric.append(c)
    return {"numeric": numeric, "categorical": categorical, "binary": binary, "all": feature_cols}


def build_tree_preprocessor(numeric_cols: list[str], categorical_cols: list[str]) -> ColumnTransformer:
    numeric_pipe = Pipeline([("impute", SimpleImputer(strategy="median"))])
    categorical_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="constant", fill_value="missing")),
        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    return ColumnTransformer([
        ("num", numeric_pipe, numeric_cols),
        ("cat", categorical_pipe, categorical_cols),
    ])


def map_feature_to_source(name: str, categorical_cols: list[str]) -> str:
    for prefix in ("num__", "cat__"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    candidates = [c for c in categorical_cols if name == c or name.startswith(c + "_")]
    if candidates:
        return max(candidates, key=len)
    return name


def safe_mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = np.abs(y_true) > 1e-8
    if mask.sum() == 0:
        return float("nan")
    return float(mean_absolute_percentage_error(y_true[mask], y_pred[mask]) * 100.0)


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    return {
        "r2": float(r2_score(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "median_ae": float(median_absolute_error(y_true, y_pred)),
        "mape_pct": safe_mape(np.asarray(y_true), np.asarray(y_pred)),
    }


def full_metric_block(y: dict[str, np.ndarray], pred: dict[str, np.ndarray]) -> dict[str, Any]:
    block: dict[str, Any] = {}
    for split in ("train", "validation", "test"):
        m = regression_metrics(y[split], pred[split])
        for k, v in m.items():
            block[f"{split}_{k}"] = v
    return block


def _aggregate_to_source(raw: dict[str, list[float]], categorical_cols: list[str]) -> dict[str, float]:
    agg: dict[str, list[float]] = {}
    for name, drops in raw.items():
        source = map_feature_to_source(name, categorical_cols)
        agg.setdefault(source, []).extend(drops)
    return {k: float(np.mean(v)) for k, v in agg.items()}


def permutation_importance_array(
    predict_fn, X: np.ndarray, y: np.ndarray, expanded_names: list[str],
    categorical_cols: list[str], n_repeats: int = 5, seed: int = SEED,
) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    baseline = r2_score(y, predict_fn(X))
    raw: dict[str, list[float]] = {}
    n = X.shape[0]
    for i, name in enumerate(expanded_names):
        drops = []
        for _ in range(n_repeats):
            X_perm = X.copy()
            X_perm[:, i] = X_perm[rng.permutation(n), i]
            drops.append(baseline - r2_score(y, predict_fn(X_perm)))
        raw[name] = drops
    return _aggregate_to_source(raw, categorical_cols)


def permutation_importance_frame(
    predict_fn, X: pd.DataFrame, y: np.ndarray, n_repeats: int = 5, seed: int = SEED,
) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    baseline = r2_score(y, predict_fn(X))
    raw: dict[str, list[float]] = {}
    n = len(X)
    for col in X.columns:
        drops = []
        for _ in range(n_repeats):
            X_perm = X.copy()
            X_perm[col] = X_perm[col].to_numpy()[rng.permutation(n)]
            drops.append(baseline - r2_score(y, predict_fn(X_perm)))
        raw[col] = drops
    return {k: float(np.mean(v)) for k, v in raw.items()}


def manual_learning_curve(
    fit_fn, X_train, y_train, X_val, y_val, fractions=(0.1, 0.25, 0.5, 0.75, 1.0), seed: int = SEED,
) -> dict[str, list[float]]:
    rng = np.random.default_rng(seed)
    n = len(y_train)
    order = rng.permutation(n)
    train_sizes, train_scores, val_scores = [], [], []
    for frac in fractions:
        k = max(int(n * frac), 20)
        k = min(k, n)
        idx = order[:k]
        Xs = X_train.iloc[idx] if hasattr(X_train, "iloc") else X_train[idx]
        ys = y_train[idx]
        model = fit_fn(Xs, ys)
        train_scores.append(float(r2_score(ys, model.predict(Xs))))
        val_scores.append(float(r2_score(y_val, model.predict(X_val))))
        train_sizes.append(int(k))
    return {"train_sizes": train_sizes, "train_r2": train_scores, "val_r2": val_scores}


def calibrate_conformal(y_val: np.ndarray, pred_val: np.ndarray, coverage: float = 0.9) -> float:
    abs_resid = np.abs(np.asarray(y_val) - np.asarray(pred_val))
    return float(np.quantile(abs_resid, coverage))


def category_error_breakdown(df_test: pd.DataFrame, y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    out: dict[str, Any] = {}
    work = df_test.reset_index(drop=True).copy()
    work["_abs_err"] = np.abs(np.asarray(y_true) - np.asarray(y_pred))
    for col in GROUP_COLS_FOR_ANALYSIS:
        if col not in work.columns:
            continue
        grp = work.groupby(col)["_abs_err"].agg(["mean", "count"]).reset_index()
        out[col] = {str(r[col]): {"mae": float(r["mean"]), "n": int(r["count"])} for _, r in grp.iterrows()}
    return out


# ══════════════════════════════════════════════════════════════════════════
# V6-specific: load + filter + control template (uses canonical_concentration_*)
# ══════════════════════════════════════════════════════════════════════════

def load_specialist_csv(category: str, version: str = "v6") -> pd.DataFrame:
    filename = DATA_VERSION_CONFIG[version]["csv_pattern"].format(CAT=category.upper())
    path = ROOT / "data" / "raw" / filename
    if not path.exists():
        raise FileNotFoundError(f"{version} specialist file not found: {path}")
    df = pd.read_csv(path)
    if TARGET not in df.columns:
        raise RuntimeError(f"Target column '{TARGET}' not found in {path.name}")
    return df


def build_control_template_v6(train_df: pd.DataFrame) -> dict[str, Any]:
    """Mirrors the legacy control_template (train_models.py) exactly in
    scope: only treatment-related fields are overridden for the control/
    baseline prediction. physical_form is deliberately NOT included here --
    it's a cheese-identity/presentation property (like food_matrix), not a
    treatment field, so it must come from `shared` (the user's actual
    selection) and stay identical between the control and every candidate,
    same as food_matrix/matrix_ph/storage_temperature_c already do."""
    control_rows = train_df[train_df["is_control"] == 1]
    if len(control_rows) == 0:
        control_rows = train_df  # degenerate fallback, should not happen in practice
    return {
        "is_control": 1,
        "treatment_type": str(control_rows["treatment_type"].mode(dropna=True).iat[0]),
        "application_method": str(control_rows["application_method"].mode(dropna=True).iat[0]),
        "ingredient_count": int(control_rows["ingredient_count"].mode(dropna=True).iat[0]),
        "primary_ingredient_name": str(control_rows["primary_ingredient_name"].mode(dropna=True).iat[0]),
        "primary_ingredient_family": str(control_rows["primary_ingredient_family"].mode(dropna=True).iat[0]),
        "canonical_concentration_value": float(control_rows["canonical_concentration_value"].median()),
        "canonical_concentration_unit": str(control_rows["canonical_concentration_unit"].mode(dropna=True).iat[0]),
    }


def train_one(category: str, task: str, output_dir: Path, version: str = "v6") -> dict[str, Any]:
    label = f"{category}/{task}"
    print(f"\n{'=' * 70}\n=== Training specialist: {label} ({version}) ===\n{'=' * 70}")
    t_start = time.time()

    full_df = load_specialist_csv(category, version)
    task_df = full_df[full_df["model_task"] == task].reset_index(drop=True)
    if len(task_df) == 0:
        raise RuntimeError(f"No rows with model_task={task!r} in {category} specialist file")

    # canonical_concentration_value/unit already exist as columns in the
    # source files (precomputed) -- to_canonical() is used at PREDICTION time
    # to convert a user's raw-unit input, not needed again here at training time.

    base_exclude = DATA_VERSION_CONFIG[version]["exclude"]
    if "routing_category" in task_df.columns:
        assert task_df["routing_category"].eq(category).all(), (
            f"routing_category diverges from the folder/category key for {label} -- "
            f"the 1:1 assumption this registry relies on no longer holds."
        )

    # Generic rule (not a hardcoded "these are safety-only" special case): any
    # column that is 100% null within THIS specialist's own task-filtered data
    # cannot be a feature for this specialist -- this is what correctly scopes
    # e.g. initial_inoculum_log_cfu_g/growth_support to the safety specialists
    # only, without assuming in advance which columns are task-scoped.
    dynamic_exclude = [
        c for c in task_df.columns
        if c != TARGET and c not in base_exclude and task_df[c].isna().all()
    ]
    if dynamic_exclude:
        print(f"  dynamically excluding (100% null for this specialist): {dynamic_exclude}")
    exclude_cols = base_exclude + dynamic_exclude

    splits = make_context_splits(task_df, seed=SEED)
    train_df, val_df, test_df = splits["train"], splits["validation"], splits["test"]
    schema = detect_schema(train_df, TARGET, exclude=exclude_cols)
    print(f"  total rows={len(task_df)}  train={len(train_df)}  validation={len(val_df)}  test={len(test_df)}")
    print(f"  numeric={len(schema['numeric'])}  categorical={len(schema['categorical'])}  binary={len(schema['binary'])}")

    assert TARGET not in schema["all"], "Target leaked into feature list"
    for extra in exclude_cols:
        assert extra not in schema["all"], f"Excluded column leaked into feature list: {extra}"

    if len(val_df) < 15 or len(test_df) < 15:
        print(f"  WARNING: thin split (val={len(val_df)}, test={len(test_df)}) -- conformal/test metrics will be noisy")

    y_train = train_df[TARGET].to_numpy(dtype=float)
    y_val = val_df[TARGET].to_numpy(dtype=float)
    y_test = test_df[TARGET].to_numpy(dtype=float)
    y_all = {"train": y_train, "validation": y_val, "test": y_test}

    models_dir = output_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    metrics: dict[str, Any] = {}
    curves: dict[str, Any] = {}
    feature_importance: dict[str, Any] = {}
    uncertainty: dict[str, Any] = {}
    category_errors: dict[str, Any] = {}
    pred_rows: list[pd.DataFrame] = []
    n_params: dict[str, Any] = {}

    numeric_and_binary = schema["numeric"] + schema["binary"]
    categorical_cols = schema["categorical"]

    def _record_predictions(model_name: str, pred: dict[str, np.ndarray]) -> None:
        for split, df_split, y_split in (("train", train_df, y_train), ("validation", val_df, y_val), ("test", test_df, y_test)):
            block = pd.DataFrame({"model": model_name, "split": split, "y_true": y_split, "y_pred": pred[split]})
            for c in GROUP_COLS_FOR_ANALYSIS:
                if c in df_split.columns:
                    block[c] = df_split[c].to_numpy()
            pred_rows.append(block)

    print("  [1/5] shared tree preprocessing ...")
    tree_pre = build_tree_preprocessor(numeric_and_binary, categorical_cols)
    X_train_tree = tree_pre.fit_transform(train_df[numeric_and_binary + categorical_cols])
    X_val_tree = tree_pre.transform(val_df[numeric_and_binary + categorical_cols])
    X_test_tree = tree_pre.transform(test_df[numeric_and_binary + categorical_cols])
    expanded_names = list(tree_pre.get_feature_names_out())
    joblib.dump(tree_pre, models_dir / "preprocessor_tree.joblib")

    # Random Forest
    print("  [2/5] Random Forest ...")
    t0 = time.time()
    rf = RandomForestRegressor(n_estimators=400, max_depth=None, min_samples_leaf=2, random_state=SEED, n_jobs=-1)
    rf.fit(X_train_tree, y_train)
    rf_duration = time.time() - t0
    rf_pred = {"train": rf.predict(X_train_tree), "validation": rf.predict(X_val_tree), "test": rf.predict(X_test_tree)}
    metrics["random_forest"] = {**full_metric_block(y_all, rf_pred), "training_duration_sec": rf_duration}
    n_params["random_forest"] = int(sum(t.tree_.node_count for t in rf.estimators_))
    joblib.dump(rf, models_dir / "random_forest.joblib")
    _record_predictions("random_forest", rf_pred)
    uncertainty["random_forest"] = {"quantile_90": calibrate_conformal(y_val, rf_pred["validation"])}
    category_errors["random_forest"] = category_error_breakdown(test_df, y_test, rf_pred["test"])
    native_rf_imp = {name: float(v) for name, v in zip(expanded_names, rf.feature_importances_)}
    feature_importance["random_forest"] = {
        "native": _aggregate_to_source({k: [v] for k, v in native_rf_imp.items()}, categorical_cols),
        "permutation": permutation_importance_array(rf.predict, X_val_tree, y_val, expanded_names, categorical_cols),
    }
    print(f"    val R2={metrics['random_forest']['validation_r2']:.3f}  test R2={metrics['random_forest']['test_r2']:.3f}  ({rf_duration:.1f}s)")

    def _fit_rf(Xs, ys):
        m = RandomForestRegressor(n_estimators=200, max_depth=None, min_samples_leaf=2, random_state=SEED, n_jobs=-1)
        m.fit(Xs, ys)
        return m
    curves["random_forest"] = {"type": "learning_curve", **manual_learning_curve(_fit_rf, X_train_tree, y_train, X_val_tree, y_val)}

    # LightGBM
    print("  [3/5] LightGBM ...")
    import lightgbm as lgb
    t0 = time.time()
    lgbm = lgb.LGBMRegressor(
        n_estimators=2000, learning_rate=0.03, num_leaves=31, min_child_samples=20,
        subsample=0.9, colsample_bytree=0.9, random_state=SEED, n_jobs=-1, verbose=-1,
    )
    lgbm.fit(
        X_train_tree, y_train, eval_set=[(X_train_tree, y_train), (X_val_tree, y_val)],
        eval_names=["train", "validation"], eval_metric="rmse",
        callbacks=[lgb.early_stopping(stopping_rounds=50, verbose=False), lgb.log_evaluation(period=0)],
    )
    lgbm_duration = time.time() - t0
    lgbm_pred = {"train": lgbm.predict(X_train_tree), "validation": lgbm.predict(X_val_tree), "test": lgbm.predict(X_test_tree)}
    metrics["lightgbm"] = {**full_metric_block(y_all, lgbm_pred), "training_duration_sec": lgbm_duration, "best_iteration": int(lgbm.best_iteration_)}
    n_params["lightgbm"] = int(lgbm.booster_.num_trees())
    joblib.dump(lgbm, models_dir / "lightgbm.joblib")
    _record_predictions("lightgbm", lgbm_pred)
    uncertainty["lightgbm"] = {"quantile_90": calibrate_conformal(y_val, lgbm_pred["validation"])}
    category_errors["lightgbm"] = category_error_breakdown(test_df, y_test, lgbm_pred["test"])
    evals = lgbm.evals_result_
    curves["lightgbm"] = {"type": "loss_curve", "train_loss": [float(v) for v in evals["train"]["rmse"]], "val_loss": [float(v) for v in evals["validation"]["rmse"]]}
    native_lgbm_imp = {name: float(v) for name, v in zip(expanded_names, lgbm.feature_importances_)}
    feature_importance["lightgbm"] = {
        "native": _aggregate_to_source({k: [v] for k, v in native_lgbm_imp.items()}, categorical_cols),
        "permutation": permutation_importance_array(lgbm.predict, X_val_tree, y_val, expanded_names, categorical_cols),
    }
    print(f"    val R2={metrics['lightgbm']['validation_r2']:.3f}  test R2={metrics['lightgbm']['test_r2']:.3f}  best_iter={lgbm.best_iteration_}  ({lgbm_duration:.1f}s)")

    # XGBoost
    print("  [4/5] XGBoost ...")
    import xgboost as xgb
    t0 = time.time()
    xgbm = xgb.XGBRegressor(
        n_estimators=2000, learning_rate=0.03, max_depth=6, subsample=0.9, colsample_bytree=0.9,
        random_state=SEED, n_jobs=-1, eval_metric="rmse", early_stopping_rounds=50, verbosity=0,
    )
    xgbm.fit(X_train_tree, y_train, eval_set=[(X_train_tree, y_train), (X_val_tree, y_val)], verbose=False)
    xgb_duration = time.time() - t0
    xgb_pred = {"train": xgbm.predict(X_train_tree), "validation": xgbm.predict(X_val_tree), "test": xgbm.predict(X_test_tree)}
    metrics["xgboost"] = {**full_metric_block(y_all, xgb_pred), "training_duration_sec": xgb_duration, "best_iteration": int(xgbm.best_iteration)}
    n_params["xgboost"] = int(xgbm.get_booster().trees_to_dataframe()["Tree"].nunique())
    joblib.dump(xgbm, models_dir / "xgboost.joblib")
    _record_predictions("xgboost", xgb_pred)
    uncertainty["xgboost"] = {"quantile_90": calibrate_conformal(y_val, xgb_pred["validation"])}
    category_errors["xgboost"] = category_error_breakdown(test_df, y_test, xgb_pred["test"])
    evals_res = xgbm.evals_result()
    curves["xgboost"] = {"type": "loss_curve", "train_loss": [float(v) for v in evals_res["validation_0"]["rmse"]], "val_loss": [float(v) for v in evals_res["validation_1"]["rmse"]]}
    native_xgb_imp_raw = xgbm.get_booster().get_score(importance_type="gain")
    native_xgb_imp = {expanded_names[int(k[1:])]: float(v) for k, v in native_xgb_imp_raw.items()}
    feature_importance["xgboost"] = {
        "native": _aggregate_to_source({k: [v] for k, v in native_xgb_imp.items()}, categorical_cols),
        "permutation": permutation_importance_array(xgbm.predict, X_val_tree, y_val, expanded_names, categorical_cols),
    }
    print(f"    val R2={metrics['xgboost']['validation_r2']:.3f}  test R2={metrics['xgboost']['test_r2']:.3f}  best_iter={xgbm.best_iteration}  ({xgb_duration:.1f}s)")

    # EBM
    print("  [5/5] Explainable Boosting Machine ...")
    from interpret.glassbox import ExplainableBoostingRegressor
    ebm_pre = FrameImputer(numeric_and_binary, categorical_cols).fit(train_df)
    X_train_ebm = ebm_pre.transform(train_df)
    X_val_ebm = ebm_pre.transform(val_df)
    X_test_ebm = ebm_pre.transform(test_df)
    joblib.dump(ebm_pre, models_dir / "preprocessor_ebm.joblib")

    t0 = time.time()
    ebm = ExplainableBoostingRegressor(
        interactions=10, max_bins=256, learning_rate=0.02, max_rounds=3000,
        min_samples_leaf=4, outer_bags=8, random_state=SEED,
    )
    ebm.fit(X_train_ebm, y_train)
    ebm_duration = time.time() - t0
    ebm_pred = {"train": ebm.predict(X_train_ebm), "validation": ebm.predict(X_val_ebm), "test": ebm.predict(X_test_ebm)}
    metrics["ebm"] = {**full_metric_block(y_all, ebm_pred), "training_duration_sec": ebm_duration}
    n_params["ebm"] = int(len(ebm.term_features_))
    joblib.dump(ebm, models_dir / "ebm.joblib")
    _record_predictions("ebm", ebm_pred)
    uncertainty["ebm"] = {"quantile_90": calibrate_conformal(y_val, ebm_pred["validation"])}
    category_errors["ebm"] = category_error_breakdown(test_df, y_test, ebm_pred["test"])

    global_exp = ebm.explain_global()
    gd = global_exp.data()
    ebm_term_names = list(gd["names"])
    ebm_term_scores = [float(s) for s in gd["scores"]]
    native_ebm_imp = {n.replace(" & ", "__x__"): s for n, s in zip(ebm_term_names, ebm_term_scores) if " & " not in n}
    shape_functions: dict[str, Any] = {}
    for idx, name in enumerate(ebm_term_names):
        if " & " in name:
            continue
        d = global_exp.data(idx)
        shape_functions[name] = {"type": d["type"], "bin_edges_or_categories": [str(x) for x in d["names"]], "scores": [float(s) for s in d["scores"]]}
    feature_importance["ebm"] = {"native": native_ebm_imp, "permutation": permutation_importance_frame(ebm.predict, X_val_ebm, y_val)}

    def _fit_ebm(Xs, ys):
        m = ExplainableBoostingRegressor(interactions=5, max_bins=256, learning_rate=0.03, max_rounds=1200, min_samples_leaf=4, outer_bags=4, random_state=SEED)
        m.fit(Xs, ys)
        return m
    curves["ebm"] = {"type": "learning_curve", **manual_learning_curve(_fit_ebm, X_train_ebm, y_train, X_val_ebm, y_val)}
    print(f"    val R2={metrics['ebm']['validation_r2']:.3f}  test R2={metrics['ebm']['test_r2']:.3f}  ({ebm_duration:.1f}s)")

    # EBM shape functions saved separately for the /api/v6 ebm/shapes-equivalent endpoint
    (output_dir / "ebm_shapes.json").write_text(json.dumps(shape_functions, indent=2), encoding="utf-8")

    models_trained = ["random_forest", "lightgbm", "xgboost", "ebm"]
    for m in models_trained:
        metrics[m]["overfitting_gap_r2"] = metrics[m]["train_r2"] - metrics[m]["validation_r2"]
        metrics[m]["n_trainable_params"] = n_params.get(m)
    best_model = min(models_trained, key=lambda m: metrics[m]["validation_rmse"])

    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (output_dir / "feature_importance.json").write_text(json.dumps(feature_importance, indent=2), encoding="utf-8")
    (output_dir / "curves.json").write_text(json.dumps(curves, indent=2), encoding="utf-8")
    (output_dir / "uncertainty.json").write_text(json.dumps(uncertainty, indent=2), encoding="utf-8")
    (output_dir / "category_errors.json").write_text(json.dumps(category_errors, indent=2), encoding="utf-8")

    all_predictions = pd.concat(pred_rows, ignore_index=True)
    all_predictions.to_parquet(output_dir / "predictions.parquet", index=False)

    categorical_options = {c: sorted(train_df[c].dropna().astype(str).unique().tolist()) for c in categorical_cols}
    categorical_modes = {c: str(train_df[c].mode(dropna=True).iat[0]) for c in categorical_cols}
    numeric_ranges = {c: {"min": float(train_df[c].min()), "max": float(train_df[c].max()), "median": float(train_df[c].median())} for c in numeric_and_binary}
    control_template = build_control_template_v6(train_df)

    schema_out = {
        "target": TARGET,
        "data_version": version,
        "cheese_category": category,
        "routing_category": category,
        "model_task": task,
        "numeric_columns": schema["numeric"],
        "categorical_columns": categorical_cols,
        "binary_columns": schema["binary"],
        "all_feature_columns": schema["all"],
        "categorical_options": categorical_options,
        "categorical_modes": categorical_modes,
        "numeric_ranges": numeric_ranges,
        "control_template": control_template,
    }
    (output_dir / "schema.json").write_text(json.dumps(schema_out, indent=2), encoding="utf-8")

    # Reused by SpecialistModelService to build matrix/ingredient lookups
    # scoped to this specialist's own food_matrix/ingredient set.
    matrix_lookup = build_matrix_lookup(train_df)
    ingredient_lookup = build_ingredient_lookup(train_df)
    (output_dir / "matrix_lookup.json").write_text(json.dumps(matrix_lookup, indent=2), encoding="utf-8")
    (output_dir / "ingredient_lookup.json").write_text(json.dumps(ingredient_lookup, indent=2), encoding="utf-8")

    duration = time.time() - t_start
    csv_filename = DATA_VERSION_CONFIG[version]["csv_pattern"].format(CAT=category.upper())
    lower_bound_pct = None
    if "target_is_lower_bound" in task_df.columns:
        lower_bound_pct = {
            "train": float(train_df["target_is_lower_bound"].mean()),
            "validation": float(val_df["target_is_lower_bound"].mean()),
            "test": float(test_df["target_is_lower_bound"].mean()),
        }
    manifest = {
        "created_at_utc": pd.Timestamp.utcnow().isoformat(),
        "random_seed": SEED,
        "data_version": version,
        "cheese_category": category,
        "model_task": task,
        "dataset_path": f"data/raw/{csv_filename}",
        "n_total": len(task_df), "n_train": len(train_df), "n_validation": len(val_df), "n_test": len(test_df),
        "models_trained": models_trained,
        "best_model_by_validation_rmse": best_model,
        "total_training_duration_sec": duration,
        "thin_split": len(val_df) < 30 or len(test_df) < 30,
        # Reporting only -- NOT used in training/loss. A high fraction here
        # means the target is a right-censored ("at least N days") lower
        # bound for many rows; standard regression treats it as exact, so
        # R2/MAE for a specialist with a high pct here should be read with
        # that caveat, not silently corrected.
        "pct_lower_bound_target": lower_bound_pct,
    }
    (output_dir / "training_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"  Done: {label} -- best={best_model}  ({duration:.1f}s)")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", choices=CATEGORIES, default=None)
    parser.add_argument("--task", choices=TASKS, default=None)
    parser.add_argument("--data-version", choices=list(DATA_VERSION_CONFIG), default="v6")
    args = parser.parse_args()

    categories = [args.category] if args.category else CATEGORIES
    tasks = [args.task] if args.task else TASKS
    version = args.data_version
    artifacts_dir_name = DATA_VERSION_CONFIG[version]["artifacts_dir"]

    t_start = time.time()
    results = []
    for category in categories:
        for task in tasks:
            output_dir = ROOT / artifacts_dir_name / category / task
            manifest = train_one(category, task, output_dir, version=version)
            results.append(manifest)

    print(f"\n{'=' * 70}\nAll specialist training complete. Total duration: {time.time() - t_start:.1f}s\n{'=' * 70}")
    for r in results:
        print(f"  {r['cheese_category']}/{r['model_task']}: n_train={r['n_train']} best={r['best_model_by_validation_rmse']} thin_split={r['thin_split']}")


if __name__ == "__main__":
    main()
