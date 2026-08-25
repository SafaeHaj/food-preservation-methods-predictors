#!/usr/bin/env python
"""
One-off metadata patch: adds a `numeric_ranges_conditional` field to each of
the 6 existing artifacts_v6/{category}/{task}/schema.json files. Does NOT
retrain any model and does NOT touch data/raw/*.csv -- it only recomputes a
smarter statistic from the exact same (unchanged) train split
train_specialists.py already used, and merges it into the existing schema
artifact.

Why this is needed: schema.json's existing `numeric_ranges` is one flat
(min, max) per feature, pooled across every row in the specialist. For a few
fields that's actively misleading, because their meaningful scale depends on
a categorical context:

  - indicator_threshold / initial_indicator_value: scale depends on which
    (indicator_type, indicator_unit) the row is for. Verified example:
    hard/safety_endpoint's *pooled* indicator_threshold range is degenerate
    (2.0-2.0, since listeria_monocytogenes/log CFU/g is its only indicator)
    while other specialists mix log CFU/g (0-8), pH (0-14), presence/25g
    (0/1), meq peroxide/kg (0-4000+) etc. into one meaningless pooled range.
  - canonical_concentration_value: scale depends on canonical_concentration_unit.
    Verified example: hard/safety_endpoint's pooled range is 0.0-495.3,
    mixing % w/w (0.017-3.0), AU/g (52-397), IU/g (50-495), log CFU/g
    (5.0-7.6), and mg/kg (5.6-8.7) into one number that can't meaningfully
    flag extrapolation for any single unit.

`numeric_ranges_conditional` stores, per affected feature, the (min, max)
grouped by its real conditioning column(s), so model_service.py's
assess_support() can compare a submitted value against the RIGHT range
instead of the pooled one -- a smarter check on the same data, not a changed
dataset.

Usage: python patch_v6_conditional_ranges.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from model_service import make_context_splits  # noqa: E402
from train_specialists import CATEGORIES, TASKS, SEED, load_specialist_csv  # noqa: E402

ROOT = Path(__file__).resolve().parent

# feature -> the column(s) its scale actually depends on
CONDITIONAL_FIELDS: dict[str, list[str]] = {
    "indicator_threshold": ["indicator_type", "indicator_unit"],
    "initial_indicator_value": ["indicator_type", "indicator_unit"],
    "canonical_concentration_value": ["canonical_concentration_unit"],
}


def compute_conditional_ranges(train_df: pd.DataFrame) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for feature, cond_cols in CONDITIONAL_FIELDS.items():
        if feature not in train_df.columns or any(c not in train_df.columns for c in cond_cols):
            continue
        groups: dict[str, dict] = {}
        for key, g in train_df.groupby(cond_cols):
            key_tuple = key if isinstance(key, tuple) else (key,)
            key_str = "||".join(str(k) for k in key_tuple)
            vals = g[feature].dropna()
            if len(vals) == 0:
                continue
            groups[key_str] = {"min": float(vals.min()), "max": float(vals.max()), "median": float(vals.median()), "n": int(len(vals))}
        out[feature] = {"conditioned_on": cond_cols, "ranges": groups}
    return out


def main() -> None:
    for category in CATEGORIES:
        full_df = load_specialist_csv(category)
        for task in TASKS:
            schema_path = ROOT / "artifacts_v6" / category / task / "schema.json"
            if not schema_path.exists():
                print(f"SKIP {category}/{task}: no schema.json found")
                continue

            task_df = full_df[full_df["model_task"] == task].reset_index(drop=True)
            train_df = make_context_splits(task_df, seed=SEED)["train"]

            conditional = compute_conditional_ranges(train_df)
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            schema["numeric_ranges_conditional"] = conditional
            schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")

            n_groups = sum(len(v["ranges"]) for v in conditional.values())
            print(f"{category}/{task}: patched {len(conditional)} field(s), {n_groups} conditional range groups total")

    print("\nDone. No model was retrained; no CSV was modified.")


if __name__ == "__main__":
    main()
