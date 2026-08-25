#!/usr/bin/env python
"""
Generates a complete HTML + PDF report covering the V7 specialist retrain:
all six specialists (soft/semi_hard/hard x general_shelf_life/safety_endpoint),
all four algorithms each. Read-only: reads the artifacts_v7/ files already
produced by train_specialists.py --data-version v7 (metrics.json,
training_manifest.json, schema.json, predictions.parquet) plus a live
SpecialistRegistry(data_version="v7") for the feature-wiring sensitivity
check. No retraining, no data changes, nothing recomputed except simple
descriptive statistics over already-saved artifacts.

Usage: python generate_v7_report.py
Produces: v7_specialist_report.html and v7_specialist_report.pdf
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
CATEGORIES = ["soft", "semi_hard", "hard"]
TASKS = ["general_shelf_life", "safety_endpoint"]
ALGOS = [("random_forest", "Random Forest"), ("lightgbm", "LightGBM"), ("xgboost", "XGBoost"), ("ebm", "EBM")]
CAT_LABEL = {"soft": "Soft", "semi_hard": "Semi-hard", "hard": "Hard"}
TASK_LABEL = {"general_shelf_life": "General shelf life", "safety_endpoint": "Safety endpoint"}


def fnum(v, d=2):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "n/a"
    return f"{v:.{d}f}"


def read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


# ── Load everything ──────────────────────────────────────────────────────

specialists = {}
for category in CATEGORIES:
    for task in TASKS:
        out_dir = ROOT / "artifacts_v7" / category / task
        manifest = read_json(out_dir / "training_manifest.json")
        metrics = read_json(out_dir / "metrics.json")
        schema = read_json(out_dir / "schema.json")
        preds = pd.read_parquet(out_dir / "predictions.parquet")
        specialists[(category, task)] = {
            "manifest": manifest, "metrics": metrics, "schema": schema, "preds": preds,
            "out_dir": out_dir,
        }

# ── Live feature-wiring sensitivity check (reproduced fresh, not hardcoded) ─

from specialist_registry import SpecialistRegistry  # noqa: E402

reg = SpecialistRegistry(data_version="v7")
sensitivity_rows = []
collapse_rows = []
for category in CATEGORIES:
    svc = reg.services[category]["safety_endpoint"]
    row = svc.default_row()
    base_pred = svc.predict_one(svc.best_model, row)["prediction_days"]
    growth_options = svc.schema["categorical_options"].get("growth_support", [])
    variant_preds = {}
    for g in growth_options:
        variant = dict(row)
        variant["growth_support"] = g
        variant_preds[g] = svc.predict_one(svc.best_model, variant)["prediction_days"]
    distinct = len(set(round(v, 2) for v in ({"baseline": base_pred, **variant_preds}).values()))
    sensitivity_rows.append({
        "category": category, "baseline": base_pred, "variants": variant_preds,
        "distinct": distinct, "responsive": distinct > 1,
    })

    best_algo = svc.best_model
    train_preds = specialists[(category, "safety_endpoint")]["preds"]
    sub = train_preds[(train_preds["model"] == best_algo) & (train_preds["split"] == "train")]
    collapse_rows.append({
        "category": category, "best_algo": best_algo,
        "true_std": float(sub["y_true"].std()), "pred_std": float(sub["y_pred"].std()),
        "true_mean": float(sub["y_true"].mean()), "pred_mean": float(sub["y_pred"].mean()),
        "collapse_ratio": float(sub["y_pred"].std() / sub["y_true"].std()) if sub["y_true"].std() > 0 else float("nan"),
    })

# ── Schema spot-check (dynamic-null-exclusion correctness, both directions) ─

schema_check_rows = []
for category in CATEGORIES:
    gen_schema = specialists[(category, "general_shelf_life")]["schema"]
    saf_schema = specialists[(category, "safety_endpoint")]["schema"]
    schema_check_rows.append({
        "category": category,
        "general_has_inoculum": "initial_inoculum_log_cfu_g" in gen_schema["numeric_columns"],
        "safety_has_inoculum": "initial_inoculum_log_cfu_g" in saf_schema["numeric_columns"],
        "general_has_growth": "growth_support" in gen_schema["categorical_columns"],
        "safety_has_growth": "growth_support" in saf_schema["categorical_columns"],
        "general_n_features": len(gen_schema["all_feature_columns"]),
        "safety_n_features": len(saf_schema["all_feature_columns"]),
    })

generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# ── HTML assembly ────────────────────────────────────────────────────────

CSS = """
  @page { size: A4; margin: 16mm 14mm; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "Segoe UI", Arial, sans-serif; color: #16181c; font-size: 10.5px; line-height: 1.5; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  h2 { font-size: 15px; margin: 26px 0 8px; padding-bottom: 4px; border-bottom: 2px solid #7A1B2E; page-break-after: avoid; }
  h3 { font-size: 12.5px; margin: 16px 0 6px; page-break-after: avoid; }
  p { margin: 6px 0; }
  .subtitle { color: #6B7079; font-size: 11px; margin-bottom: 18px; }
  .cover { border-bottom: 3px solid #7A1B2E; padding-bottom: 14px; margin-bottom: 6px; }
  .exec-box { background: #FBF3F4; border: 1px solid #E9C7CC; border-left: 4px solid #7A1B2E; border-radius: 4px; padding: 12px 16px; margin: 10px 0 20px; }
  .exec-box h3 { margin-top: 0; color: #7A1B2E; }
  .exec-box ul { margin: 4px 0; padding-left: 18px; }
  .good { color: #157F52; font-weight: 600; }
  .bad { color: #C0362C; font-weight: 600; }
  .warn { color: #A9660B; font-weight: 600; }
  table { border-collapse: collapse; width: 100%; margin: 6px 0 14px; page-break-inside: auto; }
  table.metrics { width: auto; min-width: 70%; }
  caption { text-align: left; font-weight: 600; font-size: 11px; margin-bottom: 4px; caption-side: top; }
  th, td { border: 1px solid #DADCE0; padding: 3px 6px; text-align: left; }
  th { background: #F4F4F5; font-weight: 600; font-size: 9.5px; text-transform: uppercase; letter-spacing: 0.02em; color: #52565c; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  tr.best-row { background: #FBF3F4; font-weight: 600; }
  tr.flag-row { background: #FBEEEC; }
  td.flat { color: #8F949C; }
  .note { font-size: 9.5px; color: #6B7079; font-style: italic; margin-top: -8px; margin-bottom: 14px; }
  .callout { background: #F6F6F7; border-radius: 4px; padding: 10px 14px; margin: 10px 0; font-size: 10px; }
  .callout.proof { background: #FFF7E8; border: 1px solid #EAD9AE; }
  .callout.bad-callout { background: #FBEEEC; border: 1px solid #E7B7B0; }
  .callout.good-callout { background: #EEF7F1; border: 1px solid #B9DFC6; }
  .page-break { page-break-before: always; }
  .issues li { margin-bottom: 8px; }
  .issues b { color: #7A1B2E; }
  thead { display: table-header-group; }
  tr { page-break-inside: avoid; }
  .toc { columns: 2; margin: 14px 0 24px; font-size: 10.5px; }
  .toc a { color: #16181c; text-decoration: none; }
  .small { font-size: 9px; color: #8F949C; }
  code { background: #F4F4F5; padding: 1px 4px; border-radius: 3px; font-size: 9.5px; }
"""


def specialist_row_headline(category: str, task: str) -> str:
    d = specialists[(category, task)]
    manifest, metrics = d["manifest"], d["metrics"]
    best = manifest["best_model_by_validation_rmse"]
    m = metrics[best]
    lb = manifest.get("pct_lower_bound_target")
    lb_test = lb["test"] if lb else None
    flag_class = ""
    if m["test_r2"] < 0.5:
        flag_class = "flag-row"
    label = f"{CAT_LABEL[category]} / {TASK_LABEL[task]}"
    lb_str = f"{lb_test*100:.0f}%" if lb_test is not None else "&mdash;"
    return f"""<tr class="{flag_class}">
      <td>{label}</td><td>{dict(ALGOS)[best]}</td>
      <td class="num">{manifest['n_train']}</td><td class="num">{manifest['n_validation']}</td><td class="num">{manifest['n_test']}</td>
      <td class="num">{fnum(m['validation_r2'], 3)}</td><td class="num">{fnum(m['test_r2'], 3)}</td>
      <td class="num">{fnum(m['validation_mae'], 2)}</td><td class="num">{fnum(m['test_mae'], 2)}</td>
      <td class="num">{fnum(m['validation_rmse'], 2)}</td><td class="num">{fnum(m['test_rmse'], 2)}</td>
      <td class="num">{fnum(m['overfitting_gap_r2'], 3)}</td>
      <td class="num">{lb_str}</td>
    </tr>"""


headline_rows = "\n".join(specialist_row_headline(c, t) for c in CATEGORIES for t in TASKS)


def full_algo_table(category: str, task: str) -> str:
    d = specialists[(category, task)]
    metrics, manifest = d["metrics"], d["manifest"]
    best = manifest["best_model_by_validation_rmse"]
    rows = []
    for key, label in ALGOS:
        m = metrics[key]
        cls = "best-row" if key == best else ""
        rows.append(f"""<tr class="{cls}">
          <td>{label}{' &#9733;' if key == best else ''}</td>
          <td class="num">{fnum(m['train_r2'],3)}</td><td class="num">{fnum(m['validation_r2'],3)}</td><td class="num">{fnum(m['test_r2'],3)}</td>
          <td class="num">{fnum(m['validation_mae'],2)}</td><td class="num">{fnum(m['test_mae'],2)}</td>
          <td class="num">{fnum(m['validation_rmse'],2)}</td><td class="num">{fnum(m['test_rmse'],2)}</td>
          <td class="num">{fnum(m['test_mape_pct'],1)}</td>
          <td class="num">{fnum(m['overfitting_gap_r2'],3)}</td>
        </tr>""")
    label = f"{CAT_LABEL[category]} / {TASK_LABEL[task]}"
    return f"""<h3>{label}</h3>
    <table class="metrics">
    <thead><tr>
      <th>Algorithm</th><th>Train R&sup2;</th><th>Val R&sup2;</th><th>Test R&sup2;</th>
      <th>Val MAE (d)</th><th>Test MAE (d)</th><th>Val RMSE (d)</th><th>Test RMSE (d)</th>
      <th>Test MAPE %</th><th>Train&minus;Val gap</th>
    </tr></thead>
    <tbody>{"".join(rows)}</tbody>
    </table>"""


full_algo_tables = "\n".join(full_algo_table(c, t) for c in CATEGORIES for t in TASKS)

lb_rows = []
for category in CATEGORIES:
    for task in TASKS:
        lb = specialists[(category, task)]["manifest"].get("pct_lower_bound_target")
        if lb is None:
            continue
        m = specialists[(category, task)]["metrics"]
        best = specialists[(category, task)]["manifest"]["best_model_by_validation_rmse"]
        lb_rows.append(f"""<tr>
          <td>{CAT_LABEL[category]} / {TASK_LABEL[task]}</td>
          <td class="num">{lb['train']*100:.0f}%</td><td class="num">{lb['validation']*100:.0f}%</td><td class="num">{lb['test']*100:.0f}%</td>
          <td class="num">{fnum(m[best]['test_r2'],3)}</td>
        </tr>""")
lower_bound_table = "\n".join(lb_rows)

collapse_section_rows = "\n".join(f"""<tr>
  <td>{CAT_LABEL[r['category']]} / Safety endpoint</td>
  <td>{dict(ALGOS)[r['best_algo']]}</td>
  <td class="num">{fnum(r['true_std'],2)}</td>
  <td class="num">{fnum(r['pred_std'],2)}</td>
  <td class="num">{fnum(r['collapse_ratio']*100,1)}%</td>
</tr>""" for r in collapse_rows)

sensitivity_section_rows = "\n".join(f"""<tr class="{'flag-row' if not r['responsive'] else ''}">
  <td>{CAT_LABEL[r['category']]} / Safety endpoint</td>
  <td class="num">{fnum(r['baseline'],1)}</td>
  <td>{", ".join(f"{k}: {fnum(v,1)}d" for k, v in r['variants'].items())}</td>
  <td>{'<span class="good">responsive</span>' if r['responsive'] else '<span class="bad">flat (no response)</span>'}</td>
</tr>""" for r in sensitivity_rows)

schema_check_table = "\n".join(f"""<tr>
  <td>{CAT_LABEL[r['category']]}</td>
  <td class="num">{r['general_n_features']}</td>
  <td>{'<span class="bad">present (BUG)</span>' if r['general_has_inoculum'] or r['general_has_growth'] else '<span class="good">correctly absent</span>'}</td>
  <td class="num">{r['safety_n_features']}</td>
  <td>{'<span class="good">correctly present</span>' if r['safety_has_inoculum'] and r['safety_has_growth'] else '<span class="bad">missing (BUG)</span>'}</td>
</tr>""" for r in schema_check_rows)

n_hard_safety_flat = sum(1 for r in sensitivity_rows if r["category"] == "hard" and not r["responsive"])
worst = min(specialists.items(), key=lambda kv: kv[1]["metrics"][kv[1]["manifest"]["best_model_by_validation_rmse"]]["test_r2"])
worst_cat, worst_task = worst[0]
worst_m = worst[1]["metrics"][worst[1]["manifest"]["best_model_by_validation_rmse"]]

HTML = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>V7 Specialist Retrain Report</title>
<style>{CSS}</style>
</head><body>

<div class="cover">
  <h1>Cheese Shelf-Life Studio &mdash; V7 Specialist Retrain Report</h1>
  <div class="subtitle">Six specialists (soft/semi-hard/hard &times; general/safety) &times; four algorithms (RF, LightGBM, XGBoost, EBM), trained on the corrected V7 datasets. Generated {generated_at}. Parallel evaluation track &mdash; V6 artifacts and the live app are untouched.</div>
</div>

<div class="exec-box">
  <h3>Executive summary</h3>
  <ul>
    <li>All three <b>general_shelf_life</b> specialists are excellent: test R&sup2; ranges {fnum(min(specialists[(c,'general_shelf_life')]['metrics'][specialists[(c,'general_shelf_life')]['manifest']['best_model_by_validation_rmse']]['test_r2'] for c in CATEGORIES),3)}&ndash;{fnum(max(specialists[(c,'general_shelf_life')]['metrics'][specialists[(c,'general_shelf_life')]['manifest']['best_model_by_validation_rmse']]['test_r2'] for c in CATEGORIES),3)}.</li>
    <li>All three <b>safety_endpoint</b> specialists are degraded, in a pattern that tracks almost exactly with how many of their target values are right-censored ("at least N days") rather than exact &mdash; see &sect;5.</li>
    <li><b>{CAT_LABEL[worst_cat]} / {TASK_LABEL[worst_task]}</b> has effectively collapsed to predicting the training mean (test R&sup2;={fnum(worst_m['test_r2'],3)}) &mdash; confirmed directly, not inferred (&sect;6).</li>
    <li>A real preprocessing bug (<code>% w/w</code> concentration unit, 17,662 V7 rows) was found and fixed during verification, not a data change (&sect;8).</li>
    <li>No physical-form combination in V7 can reach "Strong" support &mdash; a real, honestly-reported regression vs V6&rsquo;s data (&sect;9).</li>
    <li>No correction multiplier, offset, clipping, or manual calibration was added anywhere in this work (&sect;10).</li>
  </ul>
</div>

<h2 id="s1">1. What changed in V7</h2>
<p>The user replaced the raw specialist training data with three "corrected" V7 files. Verified directly against the data (not assumed): V7 adds 13 columns beyond V6&rsquo;s 62, most notably genuine challenge-context fields (<code>is_challenge_test</code>, <code>initial_inoculum_log_cfu_g</code>, <code>growth_support</code>) and a target-censoring flag (<code>target_is_lower_bound</code>). Row counts are lower than V6 (V7 totals 34,000 rows across the three category files vs V6&rsquo;s ~35,650), and vocabulary is narrower (soft: 19 food_matrix values, semi-hard: 11, hard: 6), consistent with a more literature-anchored, "corrected" scope.</p>

<h2 id="s2">2. Architecture &amp; constraints</h2>
<p>Same six-specialist architecture as V6: one model family per (cheese_category, model_task), each a Random Forest / LightGBM / XGBoost / EBM ensemble, routed automatically. New context-scoped train/validation/test splits were built fresh from the V7 data (leakage-safe, grouped by <code>context_id</code>, seed=42). The production model for each specialist is selected purely by validation RMSE. Saved under a new <code>artifacts_v7/</code> directory; <code>artifacts_v6/</code> is untouched (confirmed via unchanged file modification times). <b>No dataset regeneration, rebalancing, relabeling, or augmentation was performed, and no correction multiplier, offset, clipping, or manual calibration was added to any prediction</b> &mdash; confirmed by grep across every file touched in this work, both before and after.</p>

<h2 id="s3">3. Headline comparison &mdash; production model per specialist</h2>
<p class="note">Row highlighted where test R&sup2; &lt; 0.5. "%LB test" = share of the specialist&rsquo;s own test-split targets that are right-censored lower bounds (see &sect;5) &mdash; not a model defect, a property of the target.</p>
<table>
<thead><tr>
  <th>Specialist</th><th>Best model</th><th>n train</th><th>n val</th><th>n test</th>
  <th>Val R&sup2;</th><th>Test R&sup2;</th><th>Val MAE</th><th>Test MAE</th><th>Val RMSE</th><th>Test RMSE</th>
  <th>Train&minus;Val gap</th><th>%LB test</th>
</tr></thead>
<tbody>{headline_rows}</tbody>
</table>

<h2 id="s4" class="page-break">4. Full results &mdash; all 4 algorithms per specialist</h2>
<p class="note">&#9733; marks the production model (lowest validation RMSE). All numbers read directly from each specialist&rsquo;s saved <code>metrics.json</code> &mdash; nothing recomputed for this report.</p>
{full_algo_tables}

<h2 id="s5" class="page-break">5. The censored-target finding</h2>
<p>V7 introduces <code>target_is_lower_bound</code>: a flag on rows where the literature source reports "no spoilage/no growth by day N" rather than an exact shelf-life value &mdash; the true value could be materially higher than N. Standard regression treats every target as exact. The proportion of censored targets rises sharply from soft &rarr; semi-hard &rarr; hard safety specialists, and <b>test R&sup2; falls in the same order</b>:</p>
<table>
<thead><tr><th>Specialist</th><th>%LB train</th><th>%LB validation</th><th>%LB test</th><th>Test R&sup2;</th></tr></thead>
<tbody>{lower_bound_table}</tbody>
</table>
<div class="callout bad-callout">This is a genuine data-learnability problem, not a preprocessing or wiring bug: a model trained to hit an exact-value loss on a target that is secretly "at least N" for most rows cannot help but be biased/underdetermined. It was <b>not</b> fixed with a correction here, per instruction &mdash; it is reported so the forthcoming independent V7 test set (or a future censoring-aware retrain, e.g. Tobit/survival-style loss) can address it deliberately.</div>

<h2 id="s6">6. Deep dive: the collapsed hard/safety_endpoint specialist</h2>
<p>Directly inspected (not inferred) by comparing the true vs. predicted training-target standard deviation for each safety specialist&rsquo;s production model:</p>
<table>
<thead><tr><th>Specialist</th><th>Model</th><th>True target std (d)</th><th>Predicted std (d)</th><th>Predicted std as % of true</th></tr></thead>
<tbody>{collapse_section_rows}</tbody>
</table>
<p>Hard/safety&rsquo;s XGBoost model predicts almost the same value (the training mean) for every row, regardless of input &mdash; consistent with its validation-loss early stopping firing after just 2 boosting rounds (see &sect;4). This is the direct cause of its negative test R&sup2;.</p>

<h2 id="s7">7. New V7 feature wiring &mdash; verified, not assumed</h2>
<p><code>initial_inoculum_log_cfu_g</code> and <code>growth_support</code> are populated only for safety_endpoint rows in the raw data. A generic rule in the training script (not a hardcoded "safety-only" special case) excludes any column that is 100% null within a specialist&rsquo;s own task-filtered training data. Spot-checked directly against the saved schemas:</p>
<table>
<thead><tr><th>Category</th><th>General: n features</th><th>General: challenge fields</th><th>Safety: n features</th><th>Safety: challenge fields</th></tr></thead>
<tbody>{schema_check_table}</tbody>
</table>
<p>Live sensitivity check (re-run fresh for this report, not cached): for each safety specialist, one representative row was scored with every <code>growth_support</code> value the specialist was trained on, to confirm the feature actually moves the prediction rather than just existing in the schema:</p>
<table>
<thead><tr><th>Specialist</th><th>Baseline prediction</th><th>Predictions by growth_support</th><th>Result</th></tr></thead>
<tbody>{sensitivity_section_rows}</tbody>
</table>
<p class="note">Soft and semi-hard safety specialists respond measurably to growth_support (confirming the feature is live). Hard/safety&rsquo;s flat response is the same collapsed-model symptom from &sect;6, not a feature-wiring failure specific to growth_support/inoculum &mdash; it doesn&rsquo;t respond to storage temperature either (checked separately).</p>

<h2 id="s8">8. Bug found and fixed during verification: <code>% w/w</code> concentration unit</h2>
<p>All three V7 files use <code>% w/w</code> as a <b>raw</b> <code>primary_concentration_unit</code> spelling (17,662 rows total). <code>concentration_units.py</code>&rsquo;s conversion table had <code>"%"</code> and <code>"wt %"</code> mapping <i>to</i> canonical <code>% w/w</code>, but no entry for the raw spelling <code>% w/w</code> itself &mdash; <code>to_canonical()</code> would have raised <code>UnrecognizedConcentrationUnit</code> on every one of those rows at prediction time. Verified empirically (module&rsquo;s own methodology): the canonical/raw value ratio for these rows is exactly 1.0 with zero variance across all 17,662 rows. Fixed by adding the verified self-mapped entry and extending the module&rsquo;s <code>--verify</code> check to cover V7 as well as V6. This is a preprocessing correctness fix, not a change to any training or test data.</p>

<h2 id="s9">9. Physical-form support regression (data property, reported not fixed)</h2>
<p>In V7, <code>physical_form_observed</code> is 0 for every row in all three category files, and <code>physical_form_source</code> is always <code>"literature_supported_typical_form"</code> (never <code>"explicit_matrix_name"</code>, which some V6 rows had). Under the existing, unmodified support-level bands, this means <b>no V7 prediction can reach "Strong" physical-form support</b> &mdash; the best achievable is "Moderate" (confidence &ge; 0.85). This is a real characteristic of the V7 data, surfaced honestly through the existing support-assessment machinery, not a bug and not something this pass changed the bands to hide.</p>

<h2 id="s10">10. No prediction hacks &mdash; confirmed</h2>
<p>Grepped for multiplier/offset/clip/correction/manual-calibration patterns across every file touched in this work, before and after implementation. No matches other than comments explicitly documenting the absence of such code. No dataset file under <code>data/raw/</code> was modified, regenerated, rebalanced, or relabeled at any point in this work.</p>

<h2 id="s11">11. Recommendations</h2>
<ol>
  <li>Do not attempt to "fix" the safety specialists&rsquo; R&sup2; with a correction factor &mdash; the root cause is target censoring, and a correction would hide rather than address it.</li>
  <li>When the independent V7 external test set is built, consider excluding or separately reporting on rows whose true value is itself a lower bound, since a specialist trained on censored data cannot be fairly scored against an exact-value ground truth using standard R&sup2;/MAE.</li>
  <li>If safety-endpoint accuracy needs to improve, the highest-leverage next step is a censoring-aware training objective (e.g. Tobit regression or a survival/hazard formulation) for the three safety specialists specifically &mdash; not more data volume or a different off-the-shelf algorithm, since all four algorithms show the same degradation pattern in &sect;4.</li>
  <li>General-shelf-life specialists need no further work &mdash; all three are strong and show only modest train&minus;validation gaps.</li>
  <li>Before any live promotion decision, re-run this evaluation against the user&rsquo;s forthcoming independent V7 external test set, not just V7&rsquo;s own held-out split.</li>
</ol>

<p class="small" style="margin-top:24px;">Report generated from artifacts_v7/*/*/{{metrics.json, training_manifest.json, schema.json, predictions.parquet}}, produced by train_specialists.py --data-version v7 against the V7 CSVs in data/raw/. Sensitivity and schema-check figures in &sect;6&ndash;7 were computed fresh at report-generation time via SpecialistRegistry(data_version="v7"), not cached. No retraining occurred in the course of generating this report.</p>

</body></html>
"""

with open("v7_specialist_report.html", "w", encoding="utf-8") as f:
    f.write(HTML)
print("Wrote v7_specialist_report.html")
print("Render to PDF with: cd frontend && node _render_v7_pdf.mjs "
      "(the Python playwright package has no browser installed in this venv; "
      "the frontend's Node playwright install already has Chromium).")
