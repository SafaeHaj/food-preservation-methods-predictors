#!/usr/bin/env python
"""
Evaluates the live v1 models against CHEESE_319_REAL_EXTERNAL_STRESS_TEST_CASES.xlsx --
319 real-condition cases traced to 34 distinct papers (source_rule_id holds the DOI/
PubMed link), entirely disjoint from training (data_origin='external_literature_real_condition',
training_weight=0 for every row). Read-only: does not retrain or touch any saved artifact.

quality_flag's first segment (before the first '|') is a confidence/comparison-semantics
tier, analogous to the old 100-case file's validation_priority + ground_truth_type combined:
  A_STRICT_REAL        -- exact reported value, highest confidence
  A_RANGE_REAL         -- a reported range
  B_OVERALL_REAL       -- overall/nominal shelf-life claim from the paper
  B_LOWER_BOUND_REAL   -- paper reports "no spoilage by day X" -- true value >= X
  C_STUDY_HORIZON_REAL -- value is bounded by how long the study ran (looser lower bound)
  C_SAFETY_EVENT_REAL  -- value tied to a specific pathogen/safety endpoint, not general spoilage
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", None)

from model_service import ModelService

TEST_PATH = "data/raw/CHEESE_319_REAL_EXTERNAL_STRESS_TEST_CASES.xlsx"
TARGET = "shelf_life_days"
LOWER_BOUND_TIERS = {"B_LOWER_BOUND_REAL", "C_STUDY_HORIZON_REAL", "C_SAFETY_EVENT_REAL"}

svc = ModelService()
df = pd.read_excel(TEST_PATH, sheet_name="External_Test_Cases")
df["quality_tier"] = df["quality_flag"].str.split("|").str[0]

missing = [c for c in svc.feature_cols if c not in df.columns]
if missing:
    raise RuntimeError(f"Test file is missing expected feature columns: {missing}")

rows = df[svc.feature_cols].to_dict("records")

results: dict[str, np.ndarray] = {}
for model in svc.available_models:
    preds = np.array([svc.predict_one(model, row)["prediction_days"] for row in rows])
    results[model] = preds
    df[f"pred_{model}"] = preds

best = svc.best_model
y_true = df[TARGET].to_numpy(dtype=float)


def metrics(mask: pd.Series | None, y_pred: np.ndarray) -> dict:
    yt = y_true[mask] if mask is not None else y_true
    yp = y_pred[mask] if mask is not None else y_pred
    if len(yt) == 0:
        return {"n": 0}
    err = yp - yt
    ss_res = (err ** 2).sum()
    ss_tot = ((yt - yt.mean()) ** 2).sum() if len(yt) > 1 else np.nan
    r2 = 1 - ss_res / ss_tot if ss_tot and ss_tot > 0 else np.nan
    pct = np.where(yt > 0, np.abs(err) / yt * 100, np.nan)
    return {
        "n": len(yt), "MAE": np.abs(err).mean(), "RMSE": np.sqrt((err ** 2).mean()),
        "R2": r2, "MAPE_%": np.nanmean(pct), "bias": err.mean(),
        "median_AE": np.median(np.abs(err)),
    }


def fmt(m: dict) -> str:
    if m["n"] == 0:
        return "n=0"
    return (f"n={m['n']:3d}  MAE={m['MAE']:7.2f}d  RMSE={m['RMSE']:7.2f}d  "
            f"R2={m['R2']:7.3f}  MAPE={m['MAPE_%']:6.1f}%  bias={m['bias']:+7.2f}d  medAE={m['median_AE']:6.2f}d")


print("=" * 110)
print(f"CHEESE_319_REAL_EXTERNAL_STRESS_TEST_CASES -- {len(df)} cases, 34 papers, best model = {svc.model_label(best)}")
print("=" * 110)

print("\n--- Model comparison (overall, all 319 rows, all tiers pooled) ---")
for model, preds in sorted(results.items(), key=lambda kv: np.abs(kv[1] - y_true).mean()):
    print(f"  {svc.model_label(model):32s} {fmt(metrics(None, preds))}")

print(f"\n--- {svc.model_label(best)} (best model) : by quality tier ---")
print("    (R2 on tiers with a wide true-value range is meaningful; on narrow-range tiers R2 is unstable by construction)")
for tier, g in df.groupby("quality_tier"):
    mask = df["quality_tier"] == tier
    print(f"  {tier:22s} {fmt(metrics(mask, results[best]))}")

strict_mask = df["quality_tier"] == "A_STRICT_REAL"
print(f"\n--- A_STRICT_REAL only (n={strict_mask.sum()}) : every model, this is the tier requested for R2 ---")
for model, preds in sorted(results.items(), key=lambda kv: np.abs(kv[1][strict_mask] - y_true[strict_mask]).mean()):
    print(f"  {svc.model_label(model):32s} {fmt(metrics(strict_mask, preds))}")

print(f"\n--- {svc.model_label(best)} : by cheese_category ---")
for cat, g in df.groupby("cheese_category"):
    mask = df["cheese_category"] == cat
    print(f"  {cat:12s} {fmt(metrics(mask, results[best]))}")

print(f"\n--- {svc.model_label(best)} : by is_control ---")
for ctl, g in df.groupby("is_control"):
    mask = df["is_control"] == ctl
    label = "control" if ctl == 1 else "treatment"
    print(f"  {label:12s} {fmt(metrics(mask, results[best]))}")

lb_mask = df["quality_tier"].isin(LOWER_BOUND_TIERS)
if lb_mask.sum():
    meets = (df.loc[lb_mask, f"pred_{best}"] >= y_true[lb_mask]).mean() * 100
    under = (~(df.loc[lb_mask, f"pred_{best}"] >= y_true[lb_mask])).sum()
    print(f"\n--- Lower-bound-semantics tiers (n={lb_mask.sum()}): prediction >= reported lower bound ---")
    print(f"  {meets:.0f}% of predictions meet or exceed the reported bound ({under} under-predictions)")

print(f"\n--- Per-paper breakdown ({svc.model_label(best)}), papers with n>=8 rows ---")
paper_stats = df.groupby("source_rule_id").apply(
    lambda g: pd.Series(metrics(df.index.isin(g.index), results[best])), include_groups=False
)
paper_stats = paper_stats[paper_stats["n"] >= 8].sort_values("MAE", ascending=False)
print(paper_stats.round(2).to_string())

print(f"\n--- Worst 15 predictions ({svc.model_label(best)}, by absolute error) ---")
df["pred_best"] = results[best]
df["abs_err"] = (df["pred_best"] - y_true).abs()
worst = df.nlargest(15, "abs_err")
for _, r in worst.iterrows():
    print(f"  {r['row_id']}: {r['food_matrix']:22s} {r['quality_tier']:20s} true={r[TARGET]:7.1f}d  "
          f"pred={r['pred_best']:7.1f}d  err={r['pred_best']-r[TARGET]:+8.1f}d  cat={r['cheese_category']}")

df.to_csv("stress_test_319_predictions.csv", index=False)
print("\nFull per-row predictions written to stress_test_319_predictions.csv")
