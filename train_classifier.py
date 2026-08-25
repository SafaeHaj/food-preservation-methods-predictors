#!/usr/bin/env python
"""
Trains classifiers that predict a FORMULATION+TREATMENT COMBINATION's
efficacy class (Low / Medium / High relative shelf-life improvement over a
matched control), instead of predicting exact shelf-life days.

This is intentionally a SEPARATE artifact set from the regression pipeline
(train_models.py -> artifacts/). This script never writes to artifacts/ and
train_models.py never writes to artifacts_classification/ -- the two can be
retrained independently without risk to each other. It also does not import
anything from train_models.py (which has top-level side-effecting code that
runs a full regression retrain on import) -- only the pure, side-effect-free
make_context_splits() helper is reused from model_service.py.

Dataset: same source as the regression models --
data/raw/CHEESE_SHELF_LIFE_REVISED_READY_TO_TRAIN.xlsx (sheet: training_data)

Label construction:
  Every non-control row is matched to the control row (is_control=1) sharing
  its context_id -- same base matrix/storage/packaging, no treatment applied.
  We compute:
      rel_improvement_pct = (treated_days - control_days) / control_days * 100
  then bucket it into 3 classes using TRAIN-SPLIT-ONLY tertile cutoffs
  (computed after the leakage-safe context_id split; validation/test never
  influence where the class boundaries fall).

Usage:
    python train_classifier.py
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

warnings.filterwarnings("ignore")

from model_service import make_context_splits  # noqa: E402 -- pure function, no import-time side effects

SEED = 42
ROOT = Path(__file__).resolve().parent
XLSX_PATH = ROOT / "data" / "raw" / "CHEESE_SHELF_LIFE_REVISED_READY_TO_TRAIN.xlsx"
SHEET_NAME = "training_data"
ARTIFACTS_DIR = ROOT / "artifacts_classification"
MODELS_DIR = ARTIFACTS_DIR / "models"
TARGET_RAW = "shelf_life_days"
ID_COLUMNS = ["row_id", "context_id", "formulation_id", "source_rule_id"]
PROVENANCE_COLUMNS = ["data_origin", "training_weight", "quality_flag"]
EXCLUDED_COLUMNS = ID_COLUMNS + PROVENANCE_COLUMNS
CLASS_NAMES = ["Low", "Medium", "High"]


# ── Schema / preprocessing helpers (kept self-contained here, mirroring
# train_models.py's approach, so this script never imports that module) ─────

def detect_schema(df: pd.DataFrame, exclude: list[str]) -> dict[str, list[str]]:
    feature_cols = [c for c in df.columns if c not in exclude]
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
    return ColumnTransformer([("num", numeric_pipe, numeric_cols), ("cat", categorical_pipe, categorical_cols)])


def map_feature_to_source(name: str, categorical_cols: list[str]) -> str:
    for prefix in ("num__", "cat__"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    candidates = [c for c in categorical_cols if name == c or name.startswith(c + "_")]
    return max(candidates, key=len) if candidates else name


def _aggregate_to_source(raw: dict[str, list[float]], categorical_cols: list[str]) -> dict[str, float]:
    agg: dict[str, list[float]] = {}
    for name, drops in raw.items():
        source = map_feature_to_source(name, categorical_cols)
        agg.setdefault(source, []).extend(drops)
    return {k: float(np.mean(v)) for k, v in agg.items()}


def permutation_importance_array(predict_fn, X, y, expanded_names, categorical_cols, n_repeats=5, seed=SEED):
    rng = np.random.default_rng(seed)
    baseline = accuracy_score(y, predict_fn(X))
    raw: dict[str, list[float]] = {}
    n = X.shape[0]
    for i, name in enumerate(expanded_names):
        drops = []
        for _ in range(n_repeats):
            X_perm = X.copy()
            X_perm[:, i] = X_perm[rng.permutation(n), i]
            drops.append(baseline - accuracy_score(y, predict_fn(X_perm)))
        raw[name] = drops
    return _aggregate_to_source(raw, categorical_cols)


def _per_class_block(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    acc = accuracy_score(y_true, y_pred)
    macro_f1 = f1_score(y_true, y_pred, average="macro", labels=CLASS_NAMES)
    prec, rec, f1, support = precision_recall_fscore_support(y_true, y_pred, labels=CLASS_NAMES, zero_division=0)
    return {
        "accuracy": float(acc), "macro_f1": float(macro_f1),
        "per_class": {cls: {"precision": float(p), "recall": float(r), "f1": float(f), "support": int(s)}
                      for cls, p, r, f, s in zip(CLASS_NAMES, prec, rec, f1, support)},
    }


# ── 1. Load data + build leakage-safe splits (same fn/seed as regression) ───

print("=== Formulation Efficacy Classifier -- Training ===\n")
t_start = time.time()

print("[1/6] Loading workbook + building leakage-safe splits ...")
full_df = pd.read_excel(XLSX_PATH, sheet_name=SHEET_NAME)
splits = make_context_splits(full_df, seed=SEED)
train_df_full, val_df_full, test_df_full = splits["train"], splits["validation"], splits["test"]


def build_labeled(df_split: pd.DataFrame) -> pd.DataFrame:
    """Match every treatment row to its context's control row and compute
    relative shelf-life improvement. Rows without a matched control are
    dropped (their context had no control row)."""
    controls = df_split[df_split["is_control"] == 1][["context_id", TARGET_RAW]].rename(
        columns={TARGET_RAW: "control_shelf_life"})
    treated = df_split[df_split["is_control"] == 0].merge(controls, on="context_id", how="left")
    treated = treated.dropna(subset=["control_shelf_life"])
    treated = treated[treated["control_shelf_life"] > 1e-6]
    treated["rel_improvement_pct"] = (
        (treated[TARGET_RAW] - treated["control_shelf_life"]) / treated["control_shelf_life"] * 100.0
    )
    return treated


train_labeled = build_labeled(train_df_full)
val_labeled = build_labeled(val_df_full)
test_labeled = build_labeled(test_df_full)

# Class cutoffs from TRAIN split only.
t1, t2 = train_labeled["rel_improvement_pct"].quantile([1 / 3, 2 / 3]).tolist()
print(f"  class cutoffs (train-split tertiles): Low < {t1:.2f}%  |  Medium {t1:.2f}-{t2:.2f}%  |  High >= {t2:.2f}%")


def assign_class(pct: pd.Series) -> pd.Series:
    return pd.cut(pct, bins=[-np.inf, t1, t2, np.inf], labels=CLASS_NAMES)


for d in (train_labeled, val_labeled, test_labeled):
    d["efficacy_class"] = assign_class(d["rel_improvement_pct"])

print(f"  train={len(train_labeled)}  validation={len(val_labeled)}  test={len(test_labeled)}")
for split_name, d in (("train", train_labeled), ("validation", val_labeled), ("test", test_labeled)):
    print(f"    {split_name} class balance: {d['efficacy_class'].value_counts().to_dict()}")

# ── 2. Feature schema -- identical feature family to the regression models,
# minus is_control (constant here: every row is a treatment row). ───────────

FEATURE_EXCLUDE = EXCLUDED_COLUMNS + [TARGET_RAW, "control_shelf_life", "rel_improvement_pct", "efficacy_class", "is_control"]
schema = detect_schema(train_labeled, exclude=FEATURE_EXCLUDE)
numeric_and_binary = schema["numeric"] + schema["binary"]
categorical_cols = schema["categorical"]
print(f"  features: numeric={len(schema['numeric'])} categorical={len(schema['categorical'])} binary={len(schema['binary'])}")

y_train = train_labeled["efficacy_class"].astype(str).to_numpy()
y_val = val_labeled["efficacy_class"].astype(str).to_numpy()
y_test = test_labeled["efficacy_class"].astype(str).to_numpy()

MODELS_DIR.mkdir(parents=True, exist_ok=True)

# ── 3. Preprocessing ──────────────────────────────────────────────────────────

print("\n[2/6] Fitting preprocessing ...")
tree_pre = build_tree_preprocessor(numeric_and_binary, categorical_cols)
X_train = tree_pre.fit_transform(train_labeled[numeric_and_binary + categorical_cols])
X_val = tree_pre.transform(val_labeled[numeric_and_binary + categorical_cols])
X_test = tree_pre.transform(test_labeled[numeric_and_binary + categorical_cols])
expanded_names = list(tree_pre.get_feature_names_out())
joblib.dump(tree_pre, MODELS_DIR / "preprocessor_tree.joblib")
print(f"  expanded feature count: {len(expanded_names)}")

metrics: dict[str, Any] = {}
confusion: dict[str, Any] = {}
feature_importance: dict[str, Any] = {}

# ── 4. Random Forest Classifier ──────────────────────────────────────────────

print("\n[3/6] Random Forest Classifier ...")
t0 = time.time()
rf = RandomForestClassifier(n_estimators=400, max_depth=None, min_samples_leaf=2, class_weight="balanced",
                             random_state=SEED, n_jobs=-1)
rf.fit(X_train, y_train)
rf_duration = time.time() - t0
rf_pred = {"train": rf.predict(X_train), "validation": rf.predict(X_val), "test": rf.predict(X_test)}
metrics["random_forest"] = {
    split: _per_class_block(y, rf_pred[split]) for split, y in (("train", y_train), ("validation", y_val), ("test", y_test))
}
metrics["random_forest"]["training_duration_sec"] = rf_duration
joblib.dump(rf, MODELS_DIR / "random_forest_classifier.joblib")
confusion["random_forest"] = {"labels": CLASS_NAMES, "matrix": confusion_matrix(y_test, rf_pred["test"], labels=CLASS_NAMES).tolist()}
print(f"  test accuracy={metrics['random_forest']['test']['accuracy']:.3f}  macro F1={metrics['random_forest']['test']['macro_f1']:.3f}  ({rf_duration:.1f}s)")

native_rf = {name: float(v) for name, v in zip(expanded_names, rf.feature_importances_)}
feature_importance["random_forest"] = {
    "native": _aggregate_to_source({k: [v] for k, v in native_rf.items()}, categorical_cols),
    "permutation": permutation_importance_array(rf.predict, X_val, y_val, expanded_names, categorical_cols),
}

# ── 5. XGBoost Classifier ────────────────────────────────────────────────────

print("\n[4/6] XGBoost Classifier ...")
import xgboost as xgb

class_to_idx = {c: i for i, c in enumerate(CLASS_NAMES)}
y_train_idx = np.array([class_to_idx[c] for c in y_train])
y_val_idx = np.array([class_to_idx[c] for c in y_val])

t0 = time.time()
xgbm = xgb.XGBClassifier(
    n_estimators=1000, learning_rate=0.03, max_depth=5, subsample=0.9, colsample_bytree=0.9,
    random_state=SEED, n_jobs=-1, eval_metric="mlogloss", early_stopping_rounds=50, verbosity=0,
    objective="multi:softprob", num_class=3,
)
xgbm.fit(X_train, y_train_idx, eval_set=[(X_train, y_train_idx), (X_val, y_val_idx)], verbose=False)
xgb_duration = time.time() - t0


def xgb_predict_labels(X) -> np.ndarray:
    idx = xgbm.predict(X)
    return np.array([CLASS_NAMES[i] for i in idx])


xgb_pred = {"train": xgb_predict_labels(X_train), "validation": xgb_predict_labels(X_val), "test": xgb_predict_labels(X_test)}
metrics["xgboost"] = {
    split: _per_class_block(y, xgb_pred[split]) for split, y in (("train", y_train), ("validation", y_val), ("test", y_test))
}
metrics["xgboost"]["training_duration_sec"] = xgb_duration
metrics["xgboost"]["best_iteration"] = int(xgbm.best_iteration)
joblib.dump(xgbm, MODELS_DIR / "xgboost_classifier.joblib")
confusion["xgboost"] = {"labels": CLASS_NAMES, "matrix": confusion_matrix(y_test, xgb_pred["test"], labels=CLASS_NAMES).tolist()}
print(f"  test accuracy={metrics['xgboost']['test']['accuracy']:.3f}  macro F1={metrics['xgboost']['test']['macro_f1']:.3f}  ({xgb_duration:.1f}s)")

native_xgb_raw = xgbm.get_booster().get_score(importance_type="gain")
native_xgb = {expanded_names[int(k[1:])]: float(v) for k, v in native_xgb_raw.items()}
feature_importance["xgboost"] = {
    "native": _aggregate_to_source({k: [v] for k, v in native_xgb.items()}, categorical_cols),
    "permutation": permutation_importance_array(xgb_predict_labels, X_val, y_val, expanded_names, categorical_cols),
}

# ── 6. Distribution summaries + artifacts ────────────────────────────────────

print("\n[5/6] Building distribution summaries ...")
all_labeled = pd.concat([train_labeled, val_labeled, test_labeled], ignore_index=True)


def _class_counts(g: pd.DataFrame) -> dict[str, int]:
    return g["efficacy_class"].value_counts().reindex(CLASS_NAMES).fillna(0).astype(int).to_dict()


class_distribution = {
    "overall": _class_counts(all_labeled),
    "by_split": {
        split: _class_counts(d) for split, d in (("train", train_labeled), ("validation", val_labeled), ("test", test_labeled))
    },
    "by_ingredient_family": {fam: _class_counts(g) for fam, g in all_labeled.groupby("primary_ingredient_family")},
    "by_cheese_category": {cat: _class_counts(g) for cat, g in all_labeled.groupby("cheese_category")},
}

print("\n[6/6] Saving artifacts ...")
best_model = max(metrics.keys(), key=lambda m: metrics[m]["test"]["macro_f1"])

(ARTIFACTS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
(ARTIFACTS_DIR / "confusion_matrix.json").write_text(json.dumps(confusion, indent=2), encoding="utf-8")
(ARTIFACTS_DIR / "feature_importance.json").write_text(json.dumps(feature_importance, indent=2), encoding="utf-8")
(ARTIFACTS_DIR / "class_distribution.json").write_text(json.dumps(class_distribution, indent=2), encoding="utf-8")

categorical_options = {c: sorted(train_labeled[c].dropna().astype(str).unique().tolist()) for c in categorical_cols}
categorical_modes = {c: str(train_labeled[c].mode(dropna=True).iat[0]) for c in categorical_cols}
numeric_ranges = {
    c: {"min": float(train_labeled[c].min()), "max": float(train_labeled[c].max()), "median": float(train_labeled[c].median())}
    for c in numeric_and_binary
}
schema_out = {
    "numeric_columns": schema["numeric"], "categorical_columns": categorical_cols, "binary_columns": schema["binary"],
    "all_feature_columns": schema["all"],
    "categorical_options": categorical_options, "categorical_modes": categorical_modes,
    "numeric_ranges": numeric_ranges,
}
(ARTIFACTS_DIR / "schema.json").write_text(json.dumps(schema_out, indent=2), encoding="utf-8")

class_definitions = {
    "class_names": CLASS_NAMES,
    "thresholds_pct": {"low_max": float(t1), "medium_max": float(t2)},
    "description": (
        f"Efficacy class is computed from each treated row's shelf-life improvement over its "
        f"matched control (same base formulation, same context_id), as a percentage. "
        f"Low: below {t1:.1f}%. Medium: {t1:.1f}% to {t2:.1f}%. High: {t2:.1f}% and above. "
        f"Cutoffs are tertiles computed on the training split only, so classes are balanced by design."
    ),
}
(ARTIFACTS_DIR / "class_definitions.json").write_text(json.dumps(class_definitions, indent=2), encoding="utf-8")

manifest = {
    "created_at_utc": pd.Timestamp.utcnow().isoformat(),
    "random_seed": SEED,
    "dataset_path": str(XLSX_PATH.relative_to(ROOT)),
    "sheet": SHEET_NAME,
    "n_total_treated_rows": len(all_labeled),
    "n_train": len(train_labeled), "n_validation": len(val_labeled), "n_test": len(test_labeled),
    "models_trained": list(metrics.keys()),
    "best_model_by_test_macro_f1": best_model,
    "total_training_duration_sec": time.time() - t_start,
}
(ARTIFACTS_DIR / "training_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

print(f"\nModels trained: {list(metrics.keys())}")
print(f"Best model (by test macro F1): {best_model}")
print(f"Total duration: {manifest['total_training_duration_sec']:.1f}s")
print(f"Artifacts saved under: {ARTIFACTS_DIR}")
print("\n=== Training complete. ===")
