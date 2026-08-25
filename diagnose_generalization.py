#!/usr/bin/env python
"""
Diagnostic pass on the external-literature validation failure. Read-only:
loads external_test_predictions.csv (already-computed predictions) and the
training workbook, and reports where/why the model generalizes badly.
Does not retrain or touch any saved artifact.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", None)

PRED_PATH = "external_test_predictions.csv"
TRAIN_PATH = "data/raw/CHEESE_SHELF_LIFE_REVISED_READY_TO_TRAIN.xlsx"
BEST_MODEL = "xgboost"
TARGET = "literature_target_days"

df = pd.read_csv(PRED_PATH)
df["pred"] = df[f"pred_{BEST_MODEL}"]
df["error"] = df["pred"] - df[TARGET]
df["abs_error"] = df["error"].abs()
df["pct_error"] = np.where(df[TARGET] > 0, df["abs_error"] / df[TARGET] * 100, np.nan)

train = pd.read_excel(TRAIN_PATH, sheet_name="training_data")


def metrics(g: pd.DataFrame) -> pd.Series:
    err = g["error"].to_numpy()
    y = g[TARGET].to_numpy()
    ss_res = (err**2).sum()
    ss_tot = ((y - y.mean())**2).sum() if len(y) > 1 else np.nan
    r2 = 1 - ss_res / ss_tot if ss_tot and ss_tot > 0 else np.nan
    return pd.Series({
        "n": len(g),
        "MAE": np.abs(err).mean(),
        "RMSE": np.sqrt((err**2).mean()),
        "R2": r2,
        "MAPE_%": g["pct_error"].mean(),
        "mean_bias": err.mean(),
    })


print("=" * 100)
print("STEP 3: METRICS BREAKDOWN")
print("=" * 100)

print("\n--- Overall ---")
print(metrics(df).round(2))

for col in ("cheese_category", "food_matrix", "indicator_type"):
    print(f"\n--- By {col} ---")
    out = df.groupby(col, group_keys=True).apply(metrics, include_groups=False).round(2)
    out = out.sort_values("MAE", ascending=False)
    print(out)

print("\n" + "=" * 100)
print("STEP 4: FAILURE-ANALYSIS CSV")
print("=" * 100)

failure_cols = {
    "test_case_id": "test_case_id",
    "food_matrix": "food_matrix",
    "cheese_category": "cheese_category",
    "storage_temperature_c": "temperature",
    "packaging_type": "packaging",
    "indicator_type": "indicator",
    "primary_ingredient_name": "ingredient",
    TARGET: "true_shelf_life_days",
    "pred": "prediction_days",
    "error": "error_days",
    "abs_error": "abs_error_days",
    "pct_error": "pct_error",
    "ground_truth_type": "ground_truth_type",
    "validation_priority": "validation_priority",
    "paper_url": "paper_url",
}
failure_df = df[list(failure_cols.keys())].rename(columns=failure_cols)
failure_df = failure_df.sort_values("abs_error_days", ascending=False)
failure_df.to_csv("failure_analysis.csv", index=False)
print(f"Wrote failure_analysis.csv ({len(failure_df)} rows, sorted by abs_error_days desc)")

print("\n" + "=" * 100)
print("STEP 5: WORST 30 ERRORS -- PATTERN IDENTIFICATION")
print("=" * 100)
worst30 = failure_df.head(30)
print("\nfood_matrix counts among worst 30:")
print(worst30["food_matrix"].value_counts())
print("\ncheese_category counts among worst 30:")
print(worst30["cheese_category"].value_counts())
print("\nindicator counts among worst 30:")
print(worst30["indicator"].value_counts())
print("\npackaging counts among worst 30:")
print(worst30["packaging"].value_counts())
print("\ntemperature range among worst 30:", worst30["temperature"].min(), "-", worst30["temperature"].max())
print("ground_truth_type counts among worst 30:")
print(worst30["ground_truth_type"].value_counts())
print("\nDirection of error (over vs under) among worst 30:")
print((worst30["error_days"] > 0).map({True: "over-predicts", False: "under-predicts"}).value_counts())

print("\n" + "=" * 100)
print("STEP 6: TRAINING-DATA REPRESENTATION FOR FAILURE REGIONS")
print("=" * 100)

worst_matrices = worst30["food_matrix"].unique().tolist()
print(f"\nfood_matrix values in worst-30: {worst_matrices}")
for fm in worst_matrices:
    n_train = (train["food_matrix"] == fm).sum()
    n_test = (df["food_matrix"] == fm).sum()
    if n_train > 0:
        tr_sl = train.loc[train["food_matrix"] == fm, "shelf_life_days"]
        te_sl = df.loc[df["food_matrix"] == fm, TARGET]
        print(f"\n  {fm}:")
        print(f"    training rows: {n_train}  |  external test rows: {n_test}")
        print(f"    training shelf_life_days:  min={tr_sl.min():.1f} median={tr_sl.median():.1f} mean={tr_sl.mean():.1f} max={tr_sl.max():.1f}")
        print(f"    literature shelf_life_days: min={te_sl.min():.1f} median={te_sl.median():.1f} mean={te_sl.mean():.1f} max={te_sl.max():.1f}")
    else:
        print(f"\n  {fm}: NOT PRESENT IN TRAINING DATA AT ALL ({n_test} external test rows)")

print("\n--- cheese_category-level shelf_life_days distribution: training vs literature ---")
for cat in ["hard", "semi_hard", "soft"]:
    tr = train.loc[train["cheese_category"] == cat, "shelf_life_days"]
    te = df.loc[df["cheese_category"] == cat, TARGET]
    print(f"  {cat:10s} train: n={len(tr):5d} min={tr.min():6.1f} median={tr.median():6.1f} mean={tr.mean():6.1f} max={tr.max():6.1f}  P90={tr.quantile(0.9):6.1f}")
    print(f"  {'':10s} lit:   n={len(te):5d} min={te.min():6.1f} median={te.median():6.1f} mean={te.mean():6.1f} max={te.max():6.1f}")

print("\n" + "=" * 100)
print("STEP 7: TARGET-DEFINITION CONSISTENCY CHECK")
print("=" * 100)
print("\nExternal test ground_truth_type values (what literature_target_days actually represents):")
print(df["ground_truth_type"].value_counts())
print("\nindicator_group / indicator_type present among worst-30 (proxy for what 'shelf life' means):")
print(worst30.groupby(["indicator"]).size())
print("\nTraining data indicator_group distribution (what the model was trained to predict against):")
print(train["indicator_group"].value_counts())
print("\nTraining data indicator_type distribution (top 15):")
print(train["indicator_type"].value_counts().head(15))
