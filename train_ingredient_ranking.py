#!/usr/bin/env python
"""
Ranks individual INGREDIENTS (not formulations) by their typical shelf-life
efficacy, independent of any specific matrix/concentration/storage context.
This is a deliberately different, complementary system to
train_classifier.py (which classifies a full formulation+treatment
combination) -- see that script's docstring for why the two are not the same
question. Neither script imports the other, and neither touches the other's
artifact directory.

Because "ingredient efficacy in general" is inherently an aggregate over many
different contexts an ingredient was tested in, this is not a conventional
supervised classifier trained on held-out rows. It is a ranking built two
ways, so the result is checkable rather than a black box:

  1. Descriptive: mean/std of each ingredient's relative shelf-life
     improvement over its matched control, across every row it appears in.
     Simple, transparent, but can be confounded -- if an ingredient happened
     to be tested mostly in favourable conditions, its raw mean looks better
     than the ingredient itself deserves.

  2. Regression-adjusted: a ridge-regularized linear fixed-effects model
        rel_improvement_pct ~ ingredient + cheese_category + storage_temp
                             + primary_concentration + matrix_ph
                             + matrix_water_activity + packaging_type
                             + application_method
     fit with no intercept, so every ingredient's own coefficient is its
     estimated effect *after controlling for the context it was tested in*.
     This is the primary ranking; the descriptive mean is reported alongside
     for transparency, not hidden.

Both rankings are also checked for stability: each ingredient's descriptive
mean is recomputed independently on the validation and test splits (which
never influenced the regression fit) so a ranking that only looks good on
the rows used to build it is visible as such, not silently trusted.

Usage:
    python train_ingredient_ranking.py
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
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
ARTIFACTS_DIR = ROOT / "artifacts_ingredient_ranking"
TARGET_RAW = "shelf_life_days"
CLASS_NAMES = ["Low", "Medium", "High"]
MIN_SAMPLES = 20  # below this, an ingredient's ranking is flagged low-confidence, not dropped

# Context covariates the regression controls for -- deliberately excludes
# `primary_ingredient_family` (a coarser version of the thing being ranked)
# and any identifier/provenance column.
NUMERIC_COVARIATES = ["storage_temperature_c", "primary_concentration", "matrix_ph", "matrix_water_activity"]
CATEGORICAL_COVARIATES = ["cheese_category", "packaging_type", "application_method"]


def build_labeled(df_split: pd.DataFrame) -> pd.DataFrame:
    controls = df_split[df_split["is_control"] == 1][["context_id", TARGET_RAW]].rename(
        columns={TARGET_RAW: "control_shelf_life"})
    treated = df_split[df_split["is_control"] == 0].merge(controls, on="context_id", how="left")
    treated = treated.dropna(subset=["control_shelf_life"])
    treated = treated[treated["control_shelf_life"] > 1e-6]
    treated = treated[treated["primary_ingredient_name"] != "none"]
    treated["rel_improvement_pct"] = (
        (treated[TARGET_RAW] - treated["control_shelf_life"]) / treated["control_shelf_life"] * 100.0
    )
    return treated


print("=== Ingredient Efficacy Ranking ===\n")
t_start = time.time()

print("[1/5] Loading workbook + building leakage-safe splits ...")
full_df = pd.read_excel(XLSX_PATH, sheet_name=SHEET_NAME)
splits = make_context_splits(full_df, seed=SEED)
train_labeled = build_labeled(splits["train"])
val_labeled = build_labeled(splits["validation"])
test_labeled = build_labeled(splits["test"])
print(f"  train={len(train_labeled)}  validation={len(val_labeled)}  test={len(test_labeled)}  (treated rows with a matched control)")

ingredients = sorted(train_labeled["primary_ingredient_name"].unique().tolist())
print(f"  {len(ingredients)} distinct ingredients in the train split")

# ── 2. Descriptive aggregate (train split; val/test recomputed separately
#      below purely as a stability check, never blended into the ranking) ──

print("\n[2/5] Descriptive aggregate (train split) ...")
desc = train_labeled.groupby("primary_ingredient_name")["rel_improvement_pct"].agg(
    mean="mean", std="std", median="median", min="min", max="max", count="count"
)
family_lookup = train_labeled.groupby("primary_ingredient_name")["primary_ingredient_family"].agg(
    lambda s: s.mode(dropna=True).iat[0] if len(s.mode(dropna=True)) else "unknown"
)

# ── 3. Regression-adjusted effect ────────────────────────────────────────

print("\n[3/5] Fitting ridge fixed-effects regression (controls for matrix/storage/concentration/packaging) ...")
ing_encoder = OneHotEncoder(sparse_output=False, dtype=float)
X_ing = ing_encoder.fit_transform(train_labeled[["primary_ingredient_name"]])
ing_names_out = [c.split("primary_ingredient_name_", 1)[1] for c in ing_encoder.get_feature_names_out()]

cov_encoder = OneHotEncoder(sparse_output=False, handle_unknown="ignore", dtype=float)
X_cov_cat = cov_encoder.fit_transform(train_labeled[CATEGORICAL_COVARIATES])
X_cov_num = train_labeled[NUMERIC_COVARIATES].to_numpy(dtype=float)
# Standardize numeric covariates so ridge regularization treats every column
# comparably regardless of native scale (temperature in degrees vs.
# concentration in mixed units).
X_cov_num_mean, X_cov_num_std = X_cov_num.mean(axis=0), X_cov_num.std(axis=0)
X_cov_num_std[X_cov_num_std == 0] = 1.0
X_cov_num_scaled = (X_cov_num - X_cov_num_mean) / X_cov_num_std

X_design = np.hstack([X_ing, X_cov_cat, X_cov_num_scaled])
y = train_labeled["rel_improvement_pct"].to_numpy(dtype=float)

ridge = Ridge(alpha=8.0, fit_intercept=False, random_state=SEED)
ridge.fit(X_design, y)
adjusted_effect = dict(zip(ing_names_out, ridge.coef_[: len(ing_names_out)]))
print(f"  fit on {X_design.shape[0]} rows, {X_design.shape[1]} design columns ({len(ing_names_out)} ingredients + context covariates)")
print(f"  in-sample R2: {ridge.score(X_design, y):.3f}")

# ── 4. Stability: recompute the descriptive mean independently on val/test ──

print("\n[4/5] Stability check on validation / test splits ...")
val_means = val_labeled.groupby("primary_ingredient_name")["rel_improvement_pct"].agg(mean="mean", count="count")
test_means = test_labeled.groupby("primary_ingredient_name")["rel_improvement_pct"].agg(mean="mean", count="count")

# ── 5. Assemble ranking, assign classes, save ────────────────────────────

print("\n[5/5] Assembling ranking + saving artifacts ...")
rows = []
for name in ingredients:
    d = desc.loc[name]
    row = {
        "ingredient_name": name,
        "ingredient_family": str(family_lookup.get(name, "unknown")),
        "adjusted_effect_pct": float(adjusted_effect.get(name, float("nan"))),
        "descriptive_mean_pct": float(d["mean"]),
        "descriptive_std_pct": float(d["std"]) if pd.notna(d["std"]) else 0.0,
        "descriptive_median_pct": float(d["median"]),
        "descriptive_min_pct": float(d["min"]),
        "descriptive_max_pct": float(d["max"]),
        "n_train": int(d["count"]),
        "n_validation": int(val_means.loc[name, "count"]) if name in val_means.index else 0,
        "n_test": int(test_means.loc[name, "count"]) if name in test_means.index else 0,
        "validation_mean_pct": float(val_means.loc[name, "mean"]) if name in val_means.index else None,
        "test_mean_pct": float(test_means.loc[name, "mean"]) if name in test_means.index else None,
        "low_confidence": bool(d["count"] < MIN_SAMPLES),
    }
    rows.append(row)

ranking_df = pd.DataFrame(rows).sort_values("adjusted_effect_pct", ascending=False).reset_index(drop=True)
ranking_df["rank"] = np.arange(1, len(ranking_df) + 1)

# Class cutoffs from the adjusted effect's tertiles (primary ranking).
t1, t2 = ranking_df["adjusted_effect_pct"].quantile([1 / 3, 2 / 3]).tolist()
def assign_class(v: float) -> str:
    if v < t1:
        return "Low"
    if v < t2:
        return "Medium"
    return "High"
ranking_df["efficacy_class"] = ranking_df["adjusted_effect_pct"].apply(assign_class)

# Cross-check: how often does the descriptive-mean ranking agree with the
# regression-adjusted class? Reported so the two methods' agreement is
# visible, not asserted.
desc_t1, desc_t2 = ranking_df["descriptive_mean_pct"].quantile([1 / 3, 2 / 3]).tolist()
def assign_class_desc(v: float) -> str:
    if v < desc_t1:
        return "Low"
    if v < desc_t2:
        return "Medium"
    return "High"
ranking_df["efficacy_class_descriptive"] = ranking_df["descriptive_mean_pct"].apply(assign_class_desc)
agreement_pct = float((ranking_df["efficacy_class"] == ranking_df["efficacy_class_descriptive"]).mean() * 100)

# Stability: correlation between train-split adjusted rank and test-split
# descriptive mean, restricted to ingredients with enough test-split rows to
# be meaningful.
stable_rows = ranking_df[ranking_df["n_test"] >= 10]
rank_stability_corr = (
    float(stable_rows["adjusted_effect_pct"].corr(stable_rows["test_mean_pct"], method="spearman"))
    if len(stable_rows) >= 5 else None
)

ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
(ARTIFACTS_DIR / "ingredient_rankings.json").write_text(
    json.dumps(ranking_df.to_dict("records"), indent=2), encoding="utf-8"
)

class_definitions = {
    "class_names": CLASS_NAMES,
    "primary_method": "regression_adjusted",
    "thresholds_pct": {"low_max": float(t1), "medium_max": float(t2)},
    "descriptive_thresholds_pct": {"low_max": float(desc_t1), "medium_max": float(desc_t2)},
    "min_samples_for_confidence": MIN_SAMPLES,
    "description": (
        "Each ingredient's class is based on its ridge-regression-adjusted average shelf-life "
        "improvement over a matched control, controlling for cheese category, storage temperature, "
        "concentration, pH, water activity, packaging and application method -- i.e. the ingredient's "
        "own typical contribution, not the conditions it happened to be tested under. "
        f"Low: below {t1:.1f}%. Medium: {t1:.1f}% to {t2:.1f}%. High: {t2:.1f}% and above. "
        "The simpler descriptive (unadjusted) mean is reported alongside every ingredient for "
        "transparency, and the two methods agree on class "
        f"{agreement_pct:.0f}% of the time."
    ),
}
(ARTIFACTS_DIR / "class_definitions.json").write_text(json.dumps(class_definitions, indent=2), encoding="utf-8")

manifest = {
    "created_at_utc": pd.Timestamp.utcnow().isoformat(),
    "random_seed": SEED,
    "dataset_path": str(XLSX_PATH.relative_to(ROOT)),
    "sheet": SHEET_NAME,
    "n_ingredients": len(ranking_df),
    "n_train_rows": len(train_labeled),
    "n_validation_rows": len(val_labeled),
    "n_test_rows": len(test_labeled),
    "min_samples_for_confidence": MIN_SAMPLES,
    "n_low_confidence": int(ranking_df["low_confidence"].sum()),
    "regression_covariates": {"numeric": NUMERIC_COVARIATES, "categorical": CATEGORICAL_COVARIATES},
    "regression_alpha": 8.0,
    "regression_in_sample_r2": float(ridge.score(X_design, y)),
    "descriptive_vs_adjusted_agreement_pct": agreement_pct,
    "rank_stability_spearman_vs_test_split": rank_stability_corr,
    "total_duration_sec": time.time() - t_start,
}
(ARTIFACTS_DIR / "training_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

print(f"\n{len(ranking_df)} ingredients ranked.")
print(f"Descriptive vs. regression-adjusted class agreement: {agreement_pct:.0f}%")
if rank_stability_corr is not None:
    print(f"Rank stability (train-adjusted vs. test-split descriptive, Spearman): {rank_stability_corr:.3f}")
print(f"Low-confidence ingredients (< {MIN_SAMPLES} train samples): {int(ranking_df['low_confidence'].sum())}")
print(f"\nTop 5:\n{ranking_df[['ingredient_name', 'adjusted_effect_pct', 'efficacy_class']].head(5).to_string(index=False)}")
print(f"\nBottom 5:\n{ranking_df[['ingredient_name', 'adjusted_effect_pct', 'efficacy_class']].tail(5).to_string(index=False)}")
print(f"\nArtifacts saved under: {ARTIFACTS_DIR}")
print("\n=== Done. ===")
