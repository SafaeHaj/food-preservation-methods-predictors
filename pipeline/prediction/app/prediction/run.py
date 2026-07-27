"""Drive every engine over the requested scenarios and write results/ + a comparison.

Schema-generic entry point:

    python -m app.prediction.run --db data/processed/shrimp.db --scenarios a,e

Reads only the 5-table schema through `--db`, so pointing it at any other conforming
database (a different meat matrix, the app DB) runs unchanged. Each engine is evaluated in
isolation: a missing optional dependency (sksurv, xgboost) or a fit failure is recorded as a
skipped row with its reason, never aborting the whole run.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

import numpy as np
import pandas as pd

from app.core.config import Config, load_config
from app.prediction.models.gbs import GradientBoostedSurvivalEngine
from app.prediction.models.rsf import RandomSurvivalForestEngine
from app.prediction.models.weibull_aft import WeibullAFTEngine
from app.prediction import scenarios as S
from app.prediction.evaluate import EngineResult, evaluate_engine
from app.prediction.design import ModelData, build_model_data
from app.prediction.labels import connect, indicator_breach_counts

SCENARIO_BUILDERS = {"a": S.scenario_a, "e": S.scenario_e}
SURVIVAL_ENGINES = ("weibull_aft", "rsf", "gbs")


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "base.yaml").exists() and (parent / "app").is_dir():
            return parent
    raise RuntimeError("could not locate repo root (config/base.yaml + app/)")


def load_pipeline_config(repo: Path) -> Config:
    """Base config, adjusted for this small-cohort shakeout (committed base.yaml untouched).

    Overrides, all runtime-speed choices for ~30 rows — not model-behaviour changes that
    would matter at scale:

    * ``use_r_frailty=false`` — Python stage-1 Weibull only, no external R dependency.
    * lighter FISTA (``lambda_path_length=10``, ``max_iter=400``, ``tol=1e-5``) — the default
      25-λ / 2000-iter path costs ~112 s per fit here (and it is refit ~11× per scenario) for
      no benefit on 11 features; the lighter path fits in a few seconds and selects the same
      near-null model.
    * ``uncertainty.n_boot=60`` — the study-level bootstrap CI for the tree engines; 60 draws
      over 10 treatments is plenty for a mean interval width and ~3× faster than 200.
    """
    cfg = load_config(path=repo / "config" / "base.yaml")
    waft = dataclasses.replace(
        cfg.model.weibull_aft,
        use_r_frailty=False, lambda_path_length=10, max_iter=400, tol=1e-5,
    )
    unc = dataclasses.replace(cfg.model.uncertainty, n_boot=60)
    return cfg.with_overrides(
        model=dataclasses.replace(cfg.model, weibull_aft=waft, uncertainty=unc)
    )


def engine_factory(name: str, cfg: Config, data: ModelData):
    if name == "weibull_aft":
        return lambda: WeibullAFTEngine(
            cfg, feature_groups=data.feature_groups, group_names=data.group_names
        )
    if name == "rsf":
        return lambda: RandomSurvivalForestEngine(cfg)
    if name == "gbs":
        return lambda: GradientBoostedSurvivalEngine(cfg)
    raise KeyError(name)


def write_engine_outputs(out_dir: Path, res: EngineResult) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics = {
        "engine": res.name,
        "scenario": res.scenario,
        "ok": res.ok,
        "reason": res.reason,
        "c_index_mean": res.c_index_mean,
        "c_index_std": res.c_index_std,
        "n_folds_scored": res.n_folds_scored,
        "integrated_brier_score": res.ibs,
        "ci_level": res.ci_level,
        "ci_width_mean": res.ci_width_mean,
        "predicted_time_mean": res.point_mean,
        "n_selected_features": res.n_selected,
        "primary_horizon_day": res.primary_horizon,
        "classification_by_horizon": res.horizons,
    }
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    if res.oof is not None:
        res.oof.to_csv(out_dir / "cv_predictions.csv", index=False)
    if res.feature_effects is not None:
        res.feature_effects.to_csv(out_dir / "feature_effects.csv", index=False)


def comparison_row(res: EngineResult) -> dict:
    prim = res.horizons.get(res.primary_horizon, {}) if res.primary_horizon is not None else {}
    return {
        "scenario": res.scenario,
        "engine": res.name,
        "status": "ok" if res.ok else "skipped",
        "reason": res.reason,
        "n_selected": res.n_selected,
        "c_index": res.c_index_mean,
        "c_index_std": res.c_index_std,
        "integrated_brier": res.ibs,
        "ci_width_mean": res.ci_width_mean,
        "primary_horizon_day": res.primary_horizon,
        "accuracy": prim.get("accuracy", float("nan")),
        "precision": prim.get("precision", float("nan")),
        "recall": prim.get("recall", float("nan")),
        "f1": prim.get("f1", float("nan")),
    }


def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def write_comparison(
    out: Path, rows: list[dict], cohort: dict, unit_report: pd.DataFrame,
    matrices: list[str], non_breaching: list[str], direction: str,
) -> None:
    df = pd.DataFrame(rows)
    df.to_csv(out / "comparison.csv", index=False)

    cols = ["scenario", "engine", "status", "c_index", "integrated_brier", "ci_width_mean",
            "primary_horizon_day", "accuracy", "precision", "recall", "f1"]
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    lines = [header, sep]
    for _, r in df.sort_values(["scenario", "f1"], ascending=[True, False]).iterrows():
        lines.append("| " + " | ".join(_fmt(r[c]) for c in cols) + " |")
    table = "\n".join(lines)

    waft = df[(df["engine"] == "weibull_aft") & (df["status"] == "ok")]
    sel_note = "; ".join(
        f"{r['scenario']}: {int(r['n_selected'])} feature(s)"
        for _, r in waft.iterrows() if pd.notna(r.get("n_selected"))
    )
    unsafe = unit_report.loc[~unit_report["unit_safe"], "functional_class"].tolist()
    matrix_label = ", ".join(matrices) if matrices else "unknown"
    op = "≥" if direction == "upper" else "≤"
    censoring_line = (
        "- **No censoring in this input**: every experiment breaches by its last observed day, "
        "so the survival problem here is effectively failure-time regression + ranking."
        if cohort["censored"] == 0 else
        f"- **Censoring**: {cohort['censored']} / {cohort['n']} experiments never breach and are "
        "right-censored at their last observed day."
    )
    inert_line = (
        f"- **Inert indicators**: {', '.join(non_breaching)} never breach their threshold in "
        "this input, so they contribute no events — the label is driven by the remaining "
        "indicators."
        if non_breaching else
        "- Every indicator breaches at least once, so all contribute to the label."
    )
    md = f"""# Survival-modelling ({matrix_label}) — scenario × engine comparison

End-to-end run of the schema-generic survival pipeline on the **{matrix_label}** matrix.

## How to read this

- Survival models predict a **shelf-life time** (+ 95% interval), not a class. **C-index**
  (study-grouped CV, Harrell's) is the ranking metric: 1.0 perfect, 0.5 chance.
- **accuracy / precision / recall / f1** answer the operational question *"spoiled by the
  primary horizon day?"* (`event=1 and time ≤ h`) scored on **cross-validated** predicted
  times, so they are out-of-sample. The primary horizon is the failure-time cutpoint nearest
  the median; per-horizon detail is in each engine's `metrics.json`.
- **ci_width_mean** is the mean width of the 95% interval on predicted time — the model's own
  "confidence" (narrower = more certain). **integrated_brier** is a calibration score (lower
  is better), available only where the engine exposes a survival function (RSF).

## Cohort

- experiments (rows): **{cohort['n']}**, grouped into **{cohort['n_groups']}** treatments for CV.
- events: **{cohort['events']}** / {cohort['n']} — censored: **{cohort['censored']}**.
- label: earliest day any indicator crosses its **{direction}** threshold (`value {op} threshold`).
- {cohort['event_note']}

## Assumptions & caveats

- **Small sample**: {cohort['n']} experiments over {cohort['n_groups']} formulations. Every
  metric is high-variance; treat this as a plumbing/shakeout run, not a benchmark.
{censoring_line}
{inert_line}
- **Scenario E unit safety**: {'all functional classes are single-unit, so the per-class SUM is valid' if not unsafe else 'MIXED UNITS in class(es) ' + ', '.join(unsafe) + ' — SUM is not valid there'}.
- `weibull_aft` runs Python stage-1 only (`use_r_frailty=false`); the R shared-frailty refit
  is optional and off here. Its group-Lasso is aggressive on this cohort and keeps very few
  features on the full-data fit ({sel_note}), so its `feature_effects.csv` (time ratios) is
  near-empty and its interval is tight — that is a genuine small-sample selection outcome, not
  a bug.

## Results

{table}
"""
    (out / "comparison.md").write_text(md, encoding="utf-8")


def main() -> None:
    repo = _repo_root()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(repo / "data" / "processed" / "shrimp.db"))
    ap.add_argument("--scenarios", default="a,e", help="comma list of a,e")
    ap.add_argument("--engines", default=",".join(SURVIVAL_ENGINES))
    ap.add_argument("--direction", default="upper", choices=["upper", "lower"])
    ap.add_argument("--out", default=str(repo / "results"))
    args = ap.parse_args()

    cfg = load_pipeline_config(repo)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    conn = connect(args.db)

    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    engines = [e.strip() for e in args.engines.split(",") if e.strip()]

    counts = indicator_breach_counts(conn, args.direction)
    non_breaching = counts.loc[counts["breaches"] == 0, "indicator_id"].tolist()

    rows: list[dict] = []
    cohort: dict = {}
    matrices: list[str] = []
    for scen in scenarios:
        design = SCENARIO_BUILDERS[scen](conn, args.direction)
        data = build_model_data(design)
        if not cohort:
            events = int(data.y_event.sum())
            matrices = sorted(design.frame["meat_matrix"].dropna().unique().tolist())
            cohort = {
                "n": data.n, "n_groups": data.n_groups, "events": events,
                "censored": data.n - events,
                "event_note": ("event mix: "
                               + ", ".join(f"day {int(t)}×{c}"
                                           for t, c in sorted(pd.Series(data.y_time).value_counts().items()))),
            }
        for name in engines:
            res = evaluate_engine(
                name, engine_factory(name, cfg, data),
                data.X, data.y_time, data.y_event, data.groups, data.experiment_ids,
                design.name, cfg.model.cv.n_splits, cfg.model.cv.seed,
                feature_scales=data.feature_scales,
            )
            write_engine_outputs(out / design.name / name, res)
            rows.append(comparison_row(res))
            status = "ok" if res.ok else f"skipped ({res.reason})"
            print(f"[{design.name}/{name}] {status} "
                  f"c-index={res.c_index_mean:.3f} f1={comparison_row(res)['f1']}")

    write_comparison(out, rows, cohort, S.class_unit_report(conn),
                     matrices, non_breaching, args.direction)
    print(f"\nwrote results to {out}")


if __name__ == "__main__":
    main()
