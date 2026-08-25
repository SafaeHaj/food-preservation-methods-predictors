#!/usr/bin/env python
"""
Runs the full V7 prediction pipeline (SpecialistRegistry -> ModelService,
no HTTP) against one representative row per specialist, and for the three
safety specialists specifically, checks that varying growth_support /
initial_inoculum_log_cfu_g actually changes the prediction -- proving those
new challenge-context features are wired into the model, not just present
in the schema. No correction/multiplier/offset of any kind is applied to
any output here.

Usage: python test_v7_predictions.py
"""
from __future__ import annotations

from specialist_registry import SpecialistRegistry, CATEGORIES, TASKS


def main() -> None:
    print("Loading V7 specialist registry...")
    reg = SpecialistRegistry(data_version="v7")
    print("Loaded.\n")

    for category in CATEGORIES:
        for task in TASKS:
            svc = reg.services[category].get(task)
            label = f"{category}/{task}"
            print(f"{'=' * 70}\n{label}\n{'=' * 70}")
            if svc is None:
                print("  UNAVAILABLE -- no specialist loaded")
                continue

            row = svc.default_row()
            support = reg.assess_prediction_support(category, task, row)
            if not support["can_predict"]:
                print(f"  BLOCKED: {support['reason']}")
                continue

            result = svc.predict_one(svc.best_model, row)
            print(f"  model={result['model']}  prediction={result['prediction_days']:.1f}d "
                  f"[{result['lower_bound']:.1f}, {result['upper_bound']:.1f}]")
            print(f"  support level={support['level']}")
            print(f"  physical_form={row.get('physical_form')!r} food_matrix={row.get('food_matrix')!r}")
            if "initial_inoculum_log_cfu_g" in row:
                print(f"  initial_inoculum_log_cfu_g={row['initial_inoculum_log_cfu_g']} growth_support={row.get('growth_support')!r}")

            if task == "safety_endpoint":
                print("  -- challenge-context feature sensitivity check --")
                base_pred = result["prediction_days"]
                growth_options = svc.schema["categorical_options"].get("growth_support", [])
                inoc_range = svc.schema["numeric_ranges"].get("initial_inoculum_log_cfu_g")
                seen_preds = {"baseline (default_row)": base_pred}
                for g in growth_options:
                    variant = dict(row)
                    variant["growth_support"] = g
                    pred = svc.predict_one(svc.best_model, variant)["prediction_days"]
                    seen_preds[f"growth_support={g}"] = pred
                if inoc_range:
                    for label_, v in (("inoculum=min", inoc_range["min"]), ("inoculum=max", inoc_range["max"])):
                        variant = dict(row)
                        variant["initial_inoculum_log_cfu_g"] = v
                        pred = svc.predict_one(svc.best_model, variant)["prediction_days"]
                        seen_preds[label_] = pred
                for k, v in seen_preds.items():
                    print(f"    {k}: {v:.1f}d")
                distinct = len(set(round(v, 2) for v in seen_preds.values()))
                if distinct == 1:
                    print("  WARNING: prediction did not change at all across challenge-context variants -- "
                          "feature may not be wired into the model despite being in the schema.")
                else:
                    print(f"  OK: prediction varies across challenge-context inputs ({distinct} distinct values) -- feature is live.")
            print()

    print("Done.")


if __name__ == "__main__":
    main()
