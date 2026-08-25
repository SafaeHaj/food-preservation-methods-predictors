#!/usr/bin/env python
"""
Evaluates the live V7 specialist pipeline against the user's independent
external test set (data/raw/CHEESE_SHELF_LIFE_V7_EXTERNAL_TEST_POINT_TARGETS.csv)
-- 21 real, literature-derived cases with exact ("point") targets, no
censoring, sourced independently of the V7 training data.

Uses the exact same production code path as /api/v6/predict (SpecialistRegistry
.resolve/.assess_prediction_support, ModelService.predict_one) -- no separate
approximate reimplementation. The only normalization applied is cheese_category
spelling ("semi-hard" -> "semi_hard", a pure notation difference -- cheese_category
is not even a model feature, only a routing key) and running the same
concentration-unit canonicalization a live prediction request would go through.
No food_matrix/physical_form/packaging_type/indicator_type value is remapped,
guessed, or fuzzy-matched -- values that don't match the trained vocabulary are
passed through as-is and reported by the existing support-assessment machinery,
exactly as a real live prediction would be.

Importable: run_evaluation() returns (rows_out, registry) for reuse by
generate_v7_external_report.py -- no separate reimplementation of this logic.

Usage: python evaluate_v7_external_test.py
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from specialist_registry import SpecialistRegistry
from concentration_units import to_canonical, UnrecognizedConcentrationUnit

CATEGORY_NORMALIZE = {"semi-hard": "semi_hard"}  # pure notation difference; not a model feature
ALGOS = ["random_forest", "lightgbm", "xgboost", "ebm"]
EXTERNAL_TEST_CSV = "data/raw/CHEESE_SHELF_LIFE_V7_EXTERNAL_TEST_POINT_TARGETS.csv"


def run_evaluation() -> tuple[list[dict[str, Any]], SpecialistRegistry]:
    reg = SpecialistRegistry(data_version="v7")
    # utf-8-sig, not plain utf-8 -- the file has a UTF-8 BOM, and plain
    # utf-8 leaves it as a stray ﻿ prefix on the first column name
    # ("row_id" -> "﻿row_id"). Verified at the byte level (not
    # guessed): the degree/plus-minus signs in raw_reported_condition are
    # genuinely valid UTF-8 (b"\xc2\xb1" / b"\xc2\xb0"); they only looked
    # mangled during interactive terminal inspection, which was a display
    # artifact, not a real decode error. Display-only metadata either way --
    # zero effect on any prediction, since these columns are never features.
    df = pd.read_csv(EXTERNAL_TEST_CSV, encoding="utf-8-sig")

    rows_out = []
    for _, r in df.iterrows():
        row = {k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in r.to_dict().items()}
        category_raw = row["cheese_category"]
        category = CATEGORY_NORMALIZE.get(category_raw, category_raw)
        task = row["model_task"]

        conc_note = None
        raw_unit = row.get("primary_concentration_unit")
        raw_val = row.get("primary_concentration")
        if raw_unit is not None:
            try:
                canon_val, canon_unit = to_canonical(raw_val, raw_unit)
            except UnrecognizedConcentrationUnit as exc:
                canon_val, canon_unit = None, None
                conc_note = str(exc)
            row["canonical_concentration_value"] = canon_val
            row["canonical_concentration_unit"] = canon_unit

        support = reg.assess_prediction_support(category, task, row)
        entry: dict[str, Any] = {
            "row_id": r["row_id"], "category_raw": category_raw, "category": category, "task": task,
            "food_matrix": r["food_matrix"], "true_days": float(r["shelf_life_days"]),
            "citation": r.get("citation"), "source_doi": r.get("source_doi"),
            "publication_year": r.get("publication_year"), "raw_reported_condition": r.get("raw_reported_condition"),
            "row": row,
            "can_predict": support["can_predict"], "support_level": support["level"],
            "conc_note": conc_note,
            "unseen_categoricals": support["model"]["unseen_categoricals"] if support.get("model") else [],
            "extrapolations": support["model"]["extrapolations"] if support.get("model") else [],
            "physical_form_support": support.get("physical_form"),
            "reason": support.get("reason"),
        }
        if not support["can_predict"]:
            entry["predictions"] = {}
            rows_out.append(entry)
            continue

        svc, _ = reg.resolve(category, task)
        preds = {}
        for algo in ALGOS:
            if algo in svc.available_models:
                preds[algo] = svc.predict_one(algo, row)["prediction_days"]
        entry["predictions"] = preds
        entry["best_model"] = svc.best_model
        entry["best_pred"] = preds.get(svc.best_model)
        rows_out.append(entry)

    return rows_out, reg


def metrics_block(sub: list[dict[str, Any]]) -> dict[str, float]:
    if len(sub) == 0:
        return {"n": 0, "MAE": float("nan"), "RMSE": float("nan"), "bias": float("nan"), "R2": float("nan")}
    yt = np.array([r["true_days"] for r in sub], dtype=float)
    yp = np.array([r["best_pred"] for r in sub], dtype=float)
    err = yp - yt
    ss_res = (err ** 2).sum()
    ss_tot = ((yt - yt.mean()) ** 2).sum() if len(yt) > 1 else np.nan
    r2 = 1 - ss_res / ss_tot if ss_tot and ss_tot > 0 else float("nan")
    return {
        "n": len(sub), "MAE": float(np.abs(err).mean()), "RMSE": float(np.sqrt((err ** 2).mean())),
        "bias": float(err.mean()), "R2": float(r2),
    }


def main() -> None:
    import logging
    logging.getLogger("shelf_life.model_service").setLevel(logging.ERROR)

    rows_out, _ = run_evaluation()
    out_df = pd.DataFrame([{k: v for k, v in r.items() if k != "row"} for r in rows_out])
    out_df.to_csv("v7_external_test_predictions.csv", index=False)

    pd.set_option("display.width", 200)
    n_predicted = sum(1 for r in rows_out if r["can_predict"])
    print(f"{len(rows_out)} rows loaded, {n_predicted} predicted, {len(rows_out) - n_predicted} blocked.\n")

    blocked = [r for r in rows_out if not r["can_predict"]]
    if blocked:
        print("BLOCKED rows (no prediction attempted):")
        for r in blocked:
            print(f"  {r['row_id']}: {r['reason']}")
        print()

    predicted = [r for r in rows_out if r["can_predict"]]

    print("Support level distribution (production model, all predicted rows):")
    levels: dict[str, int] = {}
    for r in predicted:
        levels[r["support_level"]] = levels.get(r["support_level"], 0) + 1
    for level, n in levels.items():
        print(f"  {level}: {n}")
    print()

    print("=== Overall (production/best-validation model per specialist) ===")
    m = metrics_block(predicted)
    print(f"  n={m['n']}  MAE={m['MAE']:.1f}d  RMSE={m['RMSE']:.1f}d  bias={m['bias']:+.1f}d  R2={m['R2']:.3f}")
    print()

    print("=== By category ===")
    for cat in ["soft", "semi_hard", "hard"]:
        sub = [r for r in predicted if r["category"] == cat]
        m = metrics_block(sub)
        if m["n"] == 0:
            continue
        print(f"  {cat:<10} n={m['n']:<3} MAE={m['MAE']:>6.1f}d  RMSE={m['RMSE']:>6.1f}d  bias={m['bias']:>+7.1f}d  R2={m['R2']:>7.3f}")
    print()

    print("=== Per-row detail ===")
    for r in rows_out:
        if not r["can_predict"]:
            continue
        reasons = [f"unseen {u['feature']}={u['value']!r}" for u in r["unseen_categoricals"]]
        if r["conc_note"]:
            reasons.append("concentration unit unrecognized")
        tag = ", ".join(reasons) if reasons else "no flags"
        print(f"  {r['row_id']:<28} {r['category']:<10} true={r['true_days']:>5.0f}d  pred={r['best_pred']:>6.1f}d  "
              f"err={r['best_pred']-r['true_days']:>+6.1f}d  [{r['support_level']}] {tag}")


if __name__ == "__main__":
    main()
