#!/usr/bin/env python
"""
Small smoke test for the shelf-life regression pipeline. Not a full test
suite by design (per project scope) — just enough to confirm the trained
artifacts are usable end to end.

Usage:
    python smoke_test.py
"""
from __future__ import annotations

import sys

import numpy as np

from model_service import BEST_MODEL_KEY, ModelService

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


def main() -> None:
    print("=== Shelf-Life Regression Smoke Test ===\n")

    service = ModelService()
    check("Service loads without error", True)
    check("Schema has no target leakage", "shelf_life_days" not in service.feature_cols)
    check("Best model recorded", service.best_model in service.models)

    sample_row = service.default_row()

    for model in service.available_models:
        try:
            result = service.predict_one(model, sample_row)
            ok = result["prediction_days"] >= 0 and np.isfinite(result["prediction_days"])
            check(f"Predict smoke test: {model}", ok, f"prediction={result['prediction_days']}")
        except Exception as exc:
            check(f"Predict smoke test: {model}", False, str(exc))

    try:
        result_best = service.predict_one(BEST_MODEL_KEY, sample_row)
        check("Best-validation-model alias resolves and predicts", result_best["prediction_days"] >= 0)
    except Exception as exc:
        check("Best-validation-model alias resolves and predicts", False, str(exc))

    # Reload consistency: build a second service instance and compare predictions.
    service2 = ModelService()
    for model in service.available_models:
        p1 = service.predict_one(model, sample_row)["prediction_days"]
        p2 = service2.predict_one(model, sample_row)["prediction_days"]
        check(f"Prediction identical after reload: {model}", abs(p1 - p2) < 1e-6, f"{p1} vs {p2}")

    # Full control-vs-candidates smoke test. Candidate-specific columns come
    # from the control template; everything else in the schema is "shared" --
    # this stays correct across dataset-schema changes without hardcoding column names.
    candidate_cols = set(service.schema["control_template"].keys()) | {"name"}
    shared = {c: sample_row[c] for c in service.feature_cols if c not in candidate_cols}
    real_ingredient = next(n for n in service.schema["categorical_options"]["primary_ingredient_name"] if n != "none")
    ing_lookup = service.ingredient_lookup[real_ingredient]
    candidate = {
        "name": "Candidate A",
        "treatment_type": next(t for t in service.schema["categorical_options"]["treatment_type"] if t != "none"),
        "primary_ingredient_name": real_ingredient,
        "primary_concentration": 1.5,
        "primary_concentration_unit": next(u for u in service.schema["categorical_options"]["primary_concentration_unit"] if u != "none"),
        **ing_lookup,
    }
    if "application_method" in service.schema["control_template"]:
        candidate["application_method"] = next(
            a for a in service.schema["categorical_options"]["application_method"] if a != "none"
        )
    if "ingredient_count" in service.schema["control_template"]:
        candidate["ingredient_count"] = 1
    candidates = [candidate]
    try:
        cmp_result = service.compare_control_vs_candidates(BEST_MODEL_KEY, shared, candidates)
        ok = (
            cmp_result["control"]["prediction_days"] >= 0
            and len(cmp_result["candidates"]) == 1
            and "absolute_improvement_days" in cmp_result["candidates"][0]
            and cmp_result["candidates"][0]["rank"] == 1
        )
        check("Full control-vs-candidate smoke test", ok)
    except Exception as exc:
        check("Full control-vs-candidate smoke test", False, str(exc))

    try:
        factors = service.local_explanation(BEST_MODEL_KEY, sample_row, top_k=5)
        check("Local explanation returns factors", len(factors) > 0)
    except Exception as exc:
        check("Local explanation returns factors", False, str(exc))

    print()
    if FAILURES:
        print(f"=== {len(FAILURES)} SMOKE TEST(S) FAILED: {FAILURES} ===")
        sys.exit(1)
    print("=== All smoke tests passed. ===")


if __name__ == "__main__":
    main()
