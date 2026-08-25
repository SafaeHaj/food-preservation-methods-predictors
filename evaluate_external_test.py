#!/usr/bin/env python
"""
Evaluate the trained models against CHEESE_100_EXTERNAL_LITERATURE_TEST_CASES.xlsx --
100 hand-curated cases sourced from published literature, entirely disjoint from
the training data (exact_feature_row_present_in_training and
direct_paper_used_in_training_provenance are both "NO" for all 100 rows).
Read-only: does not retrain or touch any saved artifact.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from model_service import ModelService

TEST_PATH = "CHEESE_100_EXTERNAL_LITERATURE_TEST_CASES.xlsx"
TARGET = "literature_target_days"

svc = ModelService()
df = pd.read_excel(TEST_PATH, sheet_name="External_Test_Cases")

missing = [c for c in svc.feature_cols if c not in df.columns]
if missing:
    raise RuntimeError(f"Test file is missing expected feature columns: {missing}")

rows = df[svc.feature_cols].to_dict("records")

results = {}
for model in svc.available_models:
    preds = np.array([svc.predict_one(model, row)["prediction_days"] for row in rows])
    results[model] = preds

df_out = df.copy()
for model, preds in results.items():
    df_out[f"pred_{model}"] = preds

best = svc.best_model
y_true = df[TARGET].to_numpy(dtype=float)
y_pred = results[best]
err = y_pred - y_true
abs_err = np.abs(err)
pct_err = np.where(y_true > 0, abs_err / y_true * 100, np.nan)

print(f"=== External literature test set: {len(df)} cases, model = {svc.model_label(best)} ===\n")

print("--- Overall (treats literature_target_days as exact ground truth for all 100 cases) ---")
print(f"MAE:  {abs_err.mean():.2f} days")
print(f"RMSE: {np.sqrt((err**2).mean()):.2f} days")
print(f"MAPE: {np.nanmean(pct_err):.1f}%")
ss_res = (err**2).sum()
ss_tot = ((y_true - y_true.mean())**2).sum()
r2 = 1 - ss_res / ss_tot
print(f"R2:   {r2:.3f}")
print(f"Mean bias (pred - true): {err.mean():+.2f} days  ({'over' if err.mean()>0 else 'under'}-predicts on average)")
print(f"Median abs error: {np.median(abs_err):.2f} days")
print()

print("--- By cheese_category ---")
for cat, g in df_out.groupby("cheese_category"):
    e = np.abs(g[f"pred_{best}"] - g[TARGET])
    print(f"  {cat:12s} n={len(g):3d}  MAE={e.mean():6.2f}d  MAPE={np.nanmean(np.where(g[TARGET]>0, e/g[TARGET]*100, np.nan)):6.1f}%")
print()

print("--- By ground_truth_type (comparison semantics differ) ---")
for gt, g in df_out.groupby("ground_truth_type"):
    e = g[f"pred_{best}"] - g[TARGET]
    ae = np.abs(e)
    print(f"  {gt:22s} n={len(g):3d}  MAE={ae.mean():6.2f}d  bias={e.mean():+6.2f}d")
print()

# LOWER_BOUND / EXACT_OR_LOWER_BOUND cases: model should predict >= target.
# Under-prediction (pred < target) is the failure mode that matters here, not
# small numeric distance -- a much longer predicted shelf life is not "wrong".
lb = df_out[df_out["ground_truth_type"].isin(["LOWER_BOUND", "EXACT_OR_LOWER_BOUND"])]
if len(lb):
    meets = (lb[f"pred_{best}"] >= lb[TARGET]).mean() * 100
    print(f"--- Lower-bound cases (n={len(lb)}): prediction >= literature lower bound ---")
    print(f"  {meets:.0f}% of predictions meet or exceed the literature lower bound")
    print()

print("--- Model comparison (overall MAE / RMSE across all 100 cases) ---")
for model, preds in sorted(results.items(), key=lambda kv: np.abs(kv[1] - y_true).mean()):
    e = preds - y_true
    print(f"  {svc.model_label(model):32s} MAE={np.abs(e).mean():6.2f}d  RMSE={np.sqrt((e**2).mean()):6.2f}d  bias={e.mean():+6.2f}d")
print()

print("--- Worst 10 predictions (by absolute error, best model) ---")
worst = df_out.assign(abs_err=abs_err).nlargest(10, "abs_err")
for _, r in worst.iterrows():
    print(f"  {r['test_case_id']}: {r['food_matrix']:24s} true={r[TARGET]:6.1f}d  pred={r[f'pred_{best}']:6.1f}d  "
          f"err={r[f'pred_{best}']-r[TARGET]:+7.1f}d  ({r['ground_truth_type']}, {r['validation_priority']})")

df_out.to_csv("external_test_predictions.csv", index=False)
print("\nFull per-row predictions written to external_test_predictions.csv")
