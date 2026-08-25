#!/usr/bin/env python
"""
Reads the six already-saved artifacts_v7/{category}/{task}/{metrics.json,
training_manifest.json} files and prints one comparison table. Nothing is
recomputed here -- these are exactly the numbers train_specialists.py wrote
during training.

Usage: python summarize_v7_results.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATEGORIES = ["soft", "semi_hard", "hard"]
TASKS = ["general_shelf_life", "safety_endpoint"]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    rows = []
    for category in CATEGORIES:
        for task in TASKS:
            out_dir = ROOT / "artifacts_v7" / category / task
            manifest_path = out_dir / "training_manifest.json"
            metrics_path = out_dir / "metrics.json"
            if not manifest_path.exists() or not metrics_path.exists():
                rows.append({"category": category, "task": task, "missing": True})
                continue
            manifest = _read_json(manifest_path)
            metrics = _read_json(metrics_path)
            best = manifest["best_model_by_validation_rmse"]
            m = metrics[best]
            lb = manifest.get("pct_lower_bound_target")
            rows.append({
                "category": category, "task": task, "missing": False,
                "best_model": best,
                "n_train": manifest["n_train"], "n_val": manifest["n_validation"], "n_test": manifest["n_test"],
                "val_r2": m["validation_r2"], "test_r2": m["test_r2"],
                "val_mae": m["validation_mae"], "test_mae": m["test_mae"],
                "val_rmse": m["validation_rmse"], "test_rmse": m["test_rmse"],
                "overfit_gap": m["overfitting_gap_r2"],
                "thin_split": manifest["thin_split"],
                "pct_lower_bound_test": lb["test"] if lb else None,
            })

    header = (
        f"{'specialist':<28} {'best':<12} {'n_tr':>6} {'n_val':>6} {'n_te':>6} "
        f"{'val_R2':>7} {'test_R2':>8} {'val_MAE':>8} {'test_MAE':>9} "
        f"{'val_RMSE':>9} {'test_RMSE':>10} {'gap':>6} {'thin':>5} {'%LB_test':>9}"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        label = f"{r['category']}/{r['task']}"
        if r["missing"]:
            print(f"{label:<28} MISSING -- training did not complete for this specialist")
            continue
        lb_str = f"{r['pct_lower_bound_test']*100:.0f}%" if r["pct_lower_bound_test"] is not None else "n/a"
        print(
            f"{label:<28} {r['best_model']:<12} {r['n_train']:>6} {r['n_val']:>6} {r['n_test']:>6} "
            f"{r['val_r2']:>7.3f} {r['test_r2']:>8.3f} {r['val_mae']:>8.2f} {r['test_mae']:>9.2f} "
            f"{r['val_rmse']:>9.2f} {r['test_rmse']:>10.2f} {r['overfit_gap']:>6.3f} "
            f"{str(r['thin_split']):>5} {lb_str:>9}"
        )

    print()
    print("Flags:")
    for r in rows:
        if r.get("missing"):
            continue
        flags = []
        if r["test_r2"] < 0.5:
            flags.append(f"LOW test R2 ({r['test_r2']:.3f})")
        if r["overfit_gap"] > 0.15:
            flags.append(f"possible overfitting (train-val R2 gap={r['overfit_gap']:.3f})")
        if r["thin_split"]:
            flags.append("thin split (val or test < 30 rows)")
        if r["pct_lower_bound_test"] is not None and r["pct_lower_bound_test"] > 0.5:
            flags.append(f"{r['pct_lower_bound_test']*100:.0f}% of test targets are censored lower-bounds -- R2/MAE read with caution")
        if flags:
            print(f"  {r['category']}/{r['task']}: " + "; ".join(flags))
    if not any(
        (r["test_r2"] < 0.5 or r["overfit_gap"] > 0.15 or r["thin_split"] or (r["pct_lower_bound_test"] or 0) > 0.5)
        for r in rows if not r.get("missing")
    ):
        print("  (none beyond the lower-bound-target caveat printed in the table above)")


if __name__ == "__main__":
    main()
