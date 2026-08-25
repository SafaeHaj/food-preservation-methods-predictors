#!/usr/bin/env python
"""
Train five independent shelf-life regression models on the model-ready
workbook and save everything the dashboard needs as plain local files
(no MLflow, no server).

Dataset (the ONLY dataset this project uses):
    data/raw/CHEESE_SHELF_LIFE_REVISED_READY_TO_TRAIN.xlsx  (sheet: training_data)

Target: shelf_life_days. Identifier columns (row_id, context_id,
formulation_id, source_rule_id) and data-provenance columns (data_origin,
training_weight, quality_flag) are excluded from features -- they describe
the row's lineage, not the product, and would leak trivially if used as
inputs. This dataset version is entirely synthetic (data_origin takes two
values, synthetic_literature_constrained and synthetic_cheese_database_anchored)
-- there is no real-paper-derived subset to stratify by, unlike the original
dataset version.

This workbook ships as one sheet with no pre-built split, so a leakage-safe
train/validation/test split is built here by grouping on context_id (rows
sharing a context are never separated across splits). make_context_splits
(in model_service.py) also stratifies by a real-vs-synthetic flag for
backward compatibility with the previous dataset version; with this dataset
that flag is constant, so it degenerates to a plain grouped 70/15/15 split.

Usage:
    python train_models.py
"""
from __future__ import annotations

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
from sklearn.inspection import permutation_importance as sk_permutation_importance
from sklearn.metrics import (
    mean_absolute_error, mean_absolute_percentage_error, mean_squared_error,
    median_absolute_error, r2_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

warnings.filterwarnings("ignore")

SEED = 42
ROOT = Path(__file__).resolve().parent
XLSX_PATH = ROOT / "data" / "raw" / "CHEESE_SHELF_LIFE_TARGETED_V4_READY_TO_TRAIN.xlsx"
SHEET_NAME = "training_data"
ARTIFACTS_DIR = ROOT / "artifacts"
MODELS_DIR = ARTIFACTS_DIR / "models"
TARGET = "shelf_life_days"
ID_COLUMNS = ["row_id", "context_id", "formulation_id", "source_rule_id"]
PROVENANCE_COLUMNS = ["data_origin", "training_weight", "quality_flag"]
EXCLUDED_COLUMNS = ID_COLUMNS + PROVENANCE_COLUMNS
GROUP_COLS_FOR_ANALYSIS = ["cheese_category", "food_matrix", "indicator_type", "is_control"]

# make_context_splits lives in model_service.py (not here) so the dashboard's
# lookup-building can reconstruct the identical train split deterministically
# without re-executing this training script.
from model_service import make_context_splits  # noqa: E402


# ── 1. Load + split ──────────────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    if not XLSX_PATH.exists():
        raise FileNotFoundError(f"Workbook not found: {XLSX_PATH}")
    df = pd.read_excel(XLSX_PATH, sheet_name=SHEET_NAME)
    if TARGET not in df.columns:
        raise RuntimeError(f"Target column '{TARGET}' not found in {SHEET_NAME}")
    missing_expected = [c for c in EXCLUDED_COLUMNS if c not in df.columns]
    if missing_expected:
        raise RuntimeError(f"Expected identifier/provenance columns missing from workbook: {missing_expected}")
    return df


def detect_schema(df: pd.DataFrame, target: str, exclude: list[str] = ()) -> dict[str, list[str]]:
    """Automatically split feature columns into numeric / categorical / binary."""
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


# ── 2. Preprocessing ─────────────────────────────────────────────────────────
# FrameImputer (the EBM preprocessor) lives in model_service.py, not here --
# joblib pickles a class by its import path, and it must resolve the same
# way whether loaded from train_models.py, model_service.py, app.py, or
# smoke_test.py. Defining it in whichever script happens to be `__main__` at
# training time would make the saved pipeline unloadable from any other entry point.
from model_service import FrameImputer  # noqa: E402


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
    """Aggregate a one-hot expanded column name (e.g. 'food_matrix_gouda_cheese')
    back to its source feature ('food_matrix') for readable importance charts."""
    for prefix in ("num__", "cat__"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    candidates = [c for c in categorical_cols if name == c or name.startswith(c + "_")]
    if candidates:
        return max(candidates, key=len)
    return name


# ── 3. Metrics ───────────────────────────────────────────────────────────────

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


# ── 4. Generic permutation importance (array + frame variants) ──────────────

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


def _aggregate_to_source(raw: dict[str, list[float]], categorical_cols: list[str]) -> dict[str, float]:
    agg: dict[str, list[float]] = {}
    for name, drops in raw.items():
        source = map_feature_to_source(name, categorical_cols)
        agg.setdefault(source, []).extend(drops)
    return {k: float(np.mean(v)) for k, v in agg.items()}


# ── 5. Manual learning curve (fixed val set, not sklearn's CV-based one) ────

def manual_learning_curve(
    fit_fn, X_train, y_train, X_val, y_val, fractions=(0.1, 0.25, 0.5, 0.75, 1.0), seed: int = SEED,
) -> dict[str, list[float]]:
    rng = np.random.default_rng(seed)
    n = len(y_train)
    order = rng.permutation(n)
    train_sizes, train_scores, val_scores = [], [], []
    for frac in fractions:
        k = max(int(n * frac), 20)
        idx = order[:k]
        Xs = X_train.iloc[idx] if hasattr(X_train, "iloc") else X_train[idx]
        ys = y_train[idx]
        model = fit_fn(Xs, ys)
        train_scores.append(float(r2_score(ys, model.predict(Xs))))
        val_scores.append(float(r2_score(y_val, model.predict(X_val))))
        train_sizes.append(int(k))
    return {"train_sizes": train_sizes, "train_r2": train_scores, "val_r2": val_scores}


# ── 6. Conformal (split-conformal residual) calibration ─────────────────────

def calibrate_conformal(y_val: np.ndarray, pred_val: np.ndarray, coverage: float = 0.9) -> float:
    """Absolute-residual split-conformal quantile computed on VALIDATION ONLY."""
    abs_resid = np.abs(np.asarray(y_val) - np.asarray(pred_val))
    return float(np.quantile(abs_resid, coverage))


def clip_nonneg(x) -> np.ndarray:
    return np.clip(np.asarray(x, dtype=float), 0.0, None)


# ── 7. Per-category test error breakdown ────────────────────────────────────

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


print(f"=== Shelf-Life Regression — Training ({SHEET_NAME}) ===\n")
t_start = time.time()

print("[1/7] Loading workbook + building leakage-safe splits + detecting schema ...")
full_df = load_data()
n_real = int((full_df["data_origin"] == "real_paper_derived").sum())
splits = make_context_splits(full_df)
train_df, val_df, test_df = splits["train"], splits["validation"], splits["test"]
schema = detect_schema(train_df, TARGET, exclude=EXCLUDED_COLUMNS)
print(f"  total rows={len(full_df)}  ({n_real} real_paper_derived, {len(full_df) - n_real} synthetic)")
print(f"  train={len(train_df)}  validation={len(val_df)}  test={len(test_df)}  (split by context_id, seed={SEED})")
for split_name, split_df in splits.items():
    n_real_split = int((split_df["data_origin"] == "real_paper_derived").sum())
    print(f"    {split_name}: {n_real_split} real rows")
print(f"  numeric={len(schema['numeric'])}  categorical={len(schema['categorical'])}  binary={len(schema['binary'])}")

assert TARGET not in schema["all"], "Target leaked into feature list"
for extra in EXCLUDED_COLUMNS:
    assert extra not in schema["all"], f"Identifier/provenance column leaked into feature list: {extra}"

y_train = train_df[TARGET].to_numpy(dtype=float)
y_val = val_df[TARGET].to_numpy(dtype=float)
y_test = test_df[TARGET].to_numpy(dtype=float)
y_all = {"train": y_train, "validation": y_val, "test": y_test}

MODELS_DIR.mkdir(parents=True, exist_ok=True)

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
        block = pd.DataFrame({
            "model": model_name, "split": split,
            "y_true": y_split, "y_pred": pred[split],
        })
        for c in GROUP_COLS_FOR_ANALYSIS:
            if c in df_split.columns:
                block[c] = df_split[c].to_numpy()
        pred_rows.append(block)


# ── Tree-based models: shared ColumnTransformer ─────────────────────────────

print("\n[2/7] Fitting shared preprocessing for Random Forest / LightGBM / XGBoost ...")
tree_pre = build_tree_preprocessor(numeric_and_binary, categorical_cols)
X_train_tree = tree_pre.fit_transform(train_df[numeric_and_binary + categorical_cols])
X_val_tree = tree_pre.transform(val_df[numeric_and_binary + categorical_cols])
X_test_tree = tree_pre.transform(test_df[numeric_and_binary + categorical_cols])
expanded_names = list(tree_pre.get_feature_names_out())
joblib.dump(tree_pre, MODELS_DIR / "preprocessor_tree.joblib")
print(f"  expanded feature count: {len(expanded_names)}")

# ── Random Forest ────────────────────────────────────────────────────────────

print("\n[3/7] Random Forest ...")
t0 = time.time()
rf = RandomForestRegressor(n_estimators=400, max_depth=None, min_samples_leaf=2, random_state=SEED, n_jobs=-1)
rf.fit(X_train_tree, y_train)
rf_duration = time.time() - t0
rf_pred = {"train": rf.predict(X_train_tree), "validation": rf.predict(X_val_tree), "test": rf.predict(X_test_tree)}
metrics["random_forest"] = {**full_metric_block(y_all, rf_pred), "training_duration_sec": rf_duration}
n_params["random_forest"] = int(sum(t.tree_.node_count for t in rf.estimators_))
joblib.dump(rf, MODELS_DIR / "random_forest.joblib")
_record_predictions("random_forest", rf_pred)
uncertainty["random_forest"] = {"quantile_90": calibrate_conformal(y_val, rf_pred["validation"])}
category_errors["random_forest"] = category_error_breakdown(test_df, y_test, rf_pred["test"])

native_rf_imp = {name: float(v) for name, v in zip(expanded_names, rf.feature_importances_)}
feature_importance["random_forest"] = {
    "native": _aggregate_to_source({k: [v] for k, v in native_rf_imp.items()}, categorical_cols),
    "permutation": permutation_importance_array(rf.predict, X_val_tree, y_val, expanded_names, categorical_cols),
}
print(f"  val R2={metrics['random_forest']['validation_r2']:.3f}  test R2={metrics['random_forest']['test_r2']:.3f}  ({rf_duration:.1f}s)")

print("  computing Random Forest learning curve ...")
def _fit_rf(Xs, ys):
    m = RandomForestRegressor(n_estimators=200, max_depth=None, min_samples_leaf=2, random_state=SEED, n_jobs=-1)
    m.fit(Xs, ys)
    return m
curves["random_forest"] = {"type": "learning_curve", **manual_learning_curve(_fit_rf, X_train_tree, y_train, X_val_tree, y_val)}

# ── LightGBM ─────────────────────────────────────────────────────────────────

print("\n[4/7] LightGBM (early stopping on validation) ...")
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
metrics["lightgbm"] = {**full_metric_block(y_all, lgbm_pred), "training_duration_sec": lgbm_duration,
                       "best_iteration": int(lgbm.best_iteration_)}
n_params["lightgbm"] = int(lgbm.booster_.num_trees())
joblib.dump(lgbm, MODELS_DIR / "lightgbm.joblib")
_record_predictions("lightgbm", lgbm_pred)
uncertainty["lightgbm"] = {"quantile_90": calibrate_conformal(y_val, lgbm_pred["validation"])}
category_errors["lightgbm"] = category_error_breakdown(test_df, y_test, lgbm_pred["test"])

evals = lgbm.evals_result_
curves["lightgbm"] = {"type": "loss_curve", "train_loss": [float(v) for v in evals["train"]["rmse"]],
                      "val_loss": [float(v) for v in evals["validation"]["rmse"]]}
native_lgbm_imp = {name: float(v) for name, v in zip(expanded_names, lgbm.feature_importances_)}
feature_importance["lightgbm"] = {
    "native": _aggregate_to_source({k: [v] for k, v in native_lgbm_imp.items()}, categorical_cols),
    "permutation": permutation_importance_array(lgbm.predict, X_val_tree, y_val, expanded_names, categorical_cols),
}
print(f"  val R2={metrics['lightgbm']['validation_r2']:.3f}  test R2={metrics['lightgbm']['test_r2']:.3f}  "
      f"best_iter={lgbm.best_iteration_}  ({lgbm_duration:.1f}s)")

# ── XGBoost ──────────────────────────────────────────────────────────────────

print("\n[5/7] XGBoost (early stopping on validation) ...")
import xgboost as xgb

t0 = time.time()
xgbm = xgb.XGBRegressor(
    n_estimators=2000, learning_rate=0.03, max_depth=6, subsample=0.9, colsample_bytree=0.9,
    random_state=SEED, n_jobs=-1, eval_metric="rmse", early_stopping_rounds=50, verbosity=0,
)
xgbm.fit(X_train_tree, y_train, eval_set=[(X_train_tree, y_train), (X_val_tree, y_val)], verbose=False)
xgb_duration = time.time() - t0
xgb_pred = {"train": xgbm.predict(X_train_tree), "validation": xgbm.predict(X_val_tree), "test": xgbm.predict(X_test_tree)}
metrics["xgboost"] = {**full_metric_block(y_all, xgb_pred), "training_duration_sec": xgb_duration,
                      "best_iteration": int(xgbm.best_iteration)}
n_params["xgboost"] = int(xgbm.get_booster().trees_to_dataframe()["Tree"].nunique())
joblib.dump(xgbm, MODELS_DIR / "xgboost.joblib")
_record_predictions("xgboost", xgb_pred)
uncertainty["xgboost"] = {"quantile_90": calibrate_conformal(y_val, xgb_pred["validation"])}
category_errors["xgboost"] = category_error_breakdown(test_df, y_test, xgb_pred["test"])

evals_res = xgbm.evals_result()
curves["xgboost"] = {"type": "loss_curve", "train_loss": [float(v) for v in evals_res["validation_0"]["rmse"]],
                     "val_loss": [float(v) for v in evals_res["validation_1"]["rmse"]]}
native_xgb_imp_raw = xgbm.get_booster().get_score(importance_type="gain")
native_xgb_imp = {expanded_names[int(k[1:])]: float(v) for k, v in native_xgb_imp_raw.items()}
feature_importance["xgboost"] = {
    "native": _aggregate_to_source({k: [v] for k, v in native_xgb_imp.items()}, categorical_cols),
    "permutation": permutation_importance_array(xgbm.predict, X_val_tree, y_val, expanded_names, categorical_cols),
}
print(f"  val R2={metrics['xgboost']['validation_r2']:.3f}  test R2={metrics['xgboost']['test_r2']:.3f}  "
      f"best_iter={xgbm.best_iteration}  ({xgb_duration:.1f}s)")

# ── Explainable Boosting Machine ─────────────────────────────────────────────

print("\n[6/7] Explainable Boosting Machine ...")
from interpret.glassbox import ExplainableBoostingRegressor

ebm_pre = FrameImputer(numeric_and_binary, categorical_cols).fit(train_df)
X_train_ebm = ebm_pre.transform(train_df)
X_val_ebm = ebm_pre.transform(val_df)
X_test_ebm = ebm_pre.transform(test_df)
joblib.dump(ebm_pre, MODELS_DIR / "preprocessor_ebm.joblib")

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
joblib.dump(ebm, MODELS_DIR / "ebm.joblib")
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
    shape_functions[name] = {
        "type": d["type"], "bin_edges_or_categories": [str(x) for x in d["names"]],
        "scores": [float(s) for s in d["scores"]],
    }
feature_importance["ebm"] = {
    "native": native_ebm_imp,
    "permutation": permutation_importance_frame(ebm.predict, X_val_ebm, y_val),
}

print("  computing EBM learning curve ...")
def _fit_ebm(Xs, ys):
    m = ExplainableBoostingRegressor(interactions=5, max_bins=256, learning_rate=0.03,
                                     max_rounds=1200, min_samples_leaf=4, outer_bags=4, random_state=SEED)
    m.fit(Xs, ys)
    return m
curves["ebm"] = {"type": "learning_curve", **manual_learning_curve(_fit_ebm, X_train_ebm, y_train, X_val_ebm, y_val)}
print(f"  val R2={metrics['ebm']['validation_r2']:.3f}  test R2={metrics['ebm']['test_r2']:.3f}  ({ebm_duration:.1f}s)")

# ── LSTM (experimental tabular benchmark) ────────────────────────────────────
# NOTE: this dataset is tabular/cross-sectional, not temporal or sequential.
# The LSTM below treats each of the (one-hot expanded) feature columns as one
# step of an artificial length-N sequence purely so an LSTM layer can be
# applied at all -- it is included as an experimental benchmark, not because
# an LSTM is a natural fit for this problem. Do not read its ranking as
# evidence that sequence models suit this data.

print("\n[7/7] LSTM (experimental tabular benchmark) ...")
lstm_available = os.environ.get("SKIP_LSTM", "0") != "1"
if not lstm_available:
    print("  SKIPPED: SKIP_LSTM=1 set")
else:
    try:
        import tensorflow as tf
        tf.random.set_seed(SEED)
        from tensorflow.keras import Input
        from tensorflow.keras.callbacks import EarlyStopping
        from tensorflow.keras.layers import LSTM, Dense
        from tensorflow.keras.models import Sequential
    except ImportError as exc:
        lstm_available = False
        print(f"  SKIPPED: tensorflow not available ({exc})")

if lstm_available:
    lstm_scaler = StandardScaler()
    X_train_lstm2d = lstm_scaler.fit_transform(X_train_tree)
    X_val_lstm2d = lstm_scaler.transform(X_val_tree)
    X_test_lstm2d = lstm_scaler.transform(X_test_tree)
    joblib.dump(lstm_scaler, MODELS_DIR / "preprocessor_lstm_scaler.joblib")

    n_features = X_train_lstm2d.shape[1]

    def to_seq(x2d: np.ndarray) -> np.ndarray:
        return x2d.reshape(x2d.shape[0], x2d.shape[1], 1)

    lstm_model = Sequential([
        Input(shape=(n_features, 1)),
        LSTM(32, return_sequences=False),
        Dense(16, activation="relu"),
        Dense(1, activation="linear"),
    ])
    lstm_model.compile(optimizer="adam", loss="mse", metrics=["mae"])

    t0 = time.time()
    history = lstm_model.fit(
        to_seq(X_train_lstm2d), y_train,
        validation_data=(to_seq(X_val_lstm2d), y_val),
        epochs=150, batch_size=64, verbose=0,
        callbacks=[EarlyStopping(monitor="val_loss", patience=15, restore_best_weights=True)],
    )
    lstm_duration = time.time() - t0
    lstm_pred = {
        "train": lstm_model.predict(to_seq(X_train_lstm2d), verbose=0).ravel(),
        "validation": lstm_model.predict(to_seq(X_val_lstm2d), verbose=0).ravel(),
        "test": lstm_model.predict(to_seq(X_test_lstm2d), verbose=0).ravel(),
    }
    metrics["lstm"] = {**full_metric_block(y_all, lstm_pred), "training_duration_sec": lstm_duration,
                       "epochs_trained": len(history.history["loss"])}
    n_params["lstm"] = int(lstm_model.count_params())
    lstm_model.save(MODELS_DIR / "lstm.keras")
    _record_predictions("lstm", lstm_pred)
    uncertainty["lstm"] = {"quantile_90": calibrate_conformal(y_val, lstm_pred["validation"])}
    category_errors["lstm"] = category_error_breakdown(test_df, y_test, lstm_pred["test"])

    curves["lstm"] = {"type": "loss_curve", "train_loss": [float(v) for v in history.history["loss"]],
                      "val_loss": [float(v) for v in history.history["val_loss"]]}

    def _lstm_predict_2d(x2d: np.ndarray) -> np.ndarray:
        return lstm_model.predict(to_seq(x2d), verbose=0).ravel()

    feature_importance["lstm"] = {
        "permutation": permutation_importance_array(_lstm_predict_2d, X_val_lstm2d, y_val, expanded_names, categorical_cols),
    }
    print(f"  val R2={metrics['lstm']['validation_r2']:.3f}  test R2={metrics['lstm']['test_r2']:.3f}  "
          f"epochs={len(history.history['loss'])}  ({lstm_duration:.1f}s)")

models_trained = ["random_forest", "lightgbm", "xgboost", "ebm"] + (["lstm"] if lstm_available else [])

# ── Save artifacts ───────────────────────────────────────────────────────────

print("\nSaving artifacts ...")

for m in models_trained:
    metrics[m]["overfitting_gap_r2"] = metrics[m]["train_r2"] - metrics[m]["validation_r2"]
    metrics[m]["n_trainable_params"] = n_params.get(m)

best_model = min(models_trained, key=lambda m: metrics[m]["validation_rmse"])

(ARTIFACTS_DIR).mkdir(parents=True, exist_ok=True)
(ARTIFACTS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
(ARTIFACTS_DIR / "feature_importance.json").write_text(json.dumps(feature_importance, indent=2), encoding="utf-8")
(ARTIFACTS_DIR / "curves.json").write_text(json.dumps(curves, indent=2), encoding="utf-8")
(ARTIFACTS_DIR / "uncertainty.json").write_text(json.dumps(uncertainty, indent=2), encoding="utf-8")
(ARTIFACTS_DIR / "category_errors.json").write_text(json.dumps(category_errors, indent=2), encoding="utf-8")

all_predictions = pd.concat(pred_rows, ignore_index=True)
all_predictions.to_parquet(ARTIFACTS_DIR / "predictions.parquet", index=False)

categorical_options = {c: sorted(train_df[c].dropna().astype(str).unique().tolist()) for c in categorical_cols}
categorical_modes = {c: str(train_df[c].mode(dropna=True).iat[0]) for c in categorical_cols}
numeric_ranges = {
    c: {"min": float(train_df[c].min()), "max": float(train_df[c].max()), "median": float(train_df[c].median())}
    for c in numeric_and_binary
}
# Control-row template built from the training split's own control rows
# (mode for categorical, median for numeric) rather than hardcoded -- this
# dataset has no control_type/formulation_type columns and no multi-ingredient
# ingredient_system columns at all (ingredient_count is always 0 or 1).
control_rows = train_df[train_df["is_control"] == 1]
control_template = {
    "is_control": 1,
    "treatment_type": str(control_rows["treatment_type"].mode(dropna=True).iat[0]),
    "application_method": str(control_rows["application_method"].mode(dropna=True).iat[0]),
    "ingredient_count": int(control_rows["ingredient_count"].mode(dropna=True).iat[0]),
    "primary_ingredient_name": str(control_rows["primary_ingredient_name"].mode(dropna=True).iat[0]),
    "primary_ingredient_family": str(control_rows["primary_ingredient_family"].mode(dropna=True).iat[0]),
    "primary_concentration": float(control_rows["primary_concentration"].median()),
    "primary_concentration_unit": str(control_rows["primary_concentration_unit"].mode(dropna=True).iat[0]),
}

schema_out = {
    "target": TARGET,
    "numeric_columns": schema["numeric"],
    "categorical_columns": categorical_cols,
    "binary_columns": schema["binary"],
    "all_feature_columns": schema["all"],
    "categorical_options": categorical_options,
    "categorical_modes": categorical_modes,
    "numeric_ranges": numeric_ranges,
    "control_template": control_template,
}
(ARTIFACTS_DIR / "schema.json").write_text(json.dumps(schema_out, indent=2), encoding="utf-8")

manifest = {
    "created_at_utc": pd.Timestamp.utcnow().isoformat(),
    "random_seed": SEED,
    "dataset_path": str(XLSX_PATH.relative_to(ROOT)),
    "sheet": SHEET_NAME,
    "n_total": len(full_df), "n_real_paper_derived": n_real, "n_synthetic": len(full_df) - n_real,
    "n_train": len(train_df), "n_validation": len(val_df), "n_test": len(test_df),
    "models_trained": models_trained,
    "lstm_available": lstm_available,
    "best_model_by_validation_rmse": best_model,
    "total_training_duration_sec": time.time() - t_start,
}
(ARTIFACTS_DIR / "training_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

print(f"\nModels trained: {models_trained}")
print(f"Best model (by validation RMSE): {best_model}")
print(f"Total duration: {manifest['total_training_duration_sec']:.1f}s")
print(f"Artifacts saved under: {ARTIFACTS_DIR}")
print("\n=== Training complete. ===")
