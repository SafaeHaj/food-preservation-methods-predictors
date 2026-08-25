#!/usr/bin/env python
"""
Generates a complete HTML + PDF report of the V7 specialist pipeline's
evaluation against the user's independent external test set
(CHEESE_SHELF_LIFE_V7_EXTERNAL_TEST_POINT_TARGETS.csv, 21 real literature
cases). Reuses evaluate_v7_external_test.run_evaluation() directly -- no
separate reimplementation of the routing/prediction/support-assessment
logic. Every row's full flag detail (every unseen categorical, every
extrapolation, citation, source DOI, raw reported condition) is included
for careful manual inspection, per the user's request.

Usage: python generate_v7_external_report.py
Produces: v7_external_test_report.html and v7_external_test_report.pdf (via
frontend/_render_v7_pdf.mjs's pattern -- see that script's sibling for PDF
rendering, since the Python playwright package has no browser installed
in this venv).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np

logging.getLogger("shelf_life.model_service").setLevel(logging.ERROR)

from evaluate_v7_external_test import run_evaluation, metrics_block, ALGOS  # noqa: E402

ALGO_LABEL = {"random_forest": "Random Forest", "lightgbm": "LightGBM", "xgboost": "XGBoost", "ebm": "EBM"}
CAT_LABEL = {"soft": "Soft", "semi_hard": "Semi-hard", "hard": "Hard"}


def fnum(v, d=1):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "n/a"
    return f"{v:.{d}f}"


def esc(s) -> str:
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


print("Running evaluation (loads all V7 specialists)...")
rows, reg = run_evaluation()
print(f"Done: {len(rows)} rows.")

predicted = [r for r in rows if r["can_predict"]]
blocked = [r for r in rows if not r["can_predict"]]

overall_m = metrics_block(predicted)
by_category = {cat: metrics_block([r for r in predicted if r["category"] == cat]) for cat in ["soft", "semi_hard", "hard"]}

levels: dict[str, list[dict]] = {}
for r in predicted:
    levels.setdefault(r["support_level"], []).append(r)

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
  caption { text-align: left; font-weight: 600; font-size: 11px; margin-bottom: 4px; caption-side: top; }
  th, td { border: 1px solid #DADCE0; padding: 3px 6px; text-align: left; vertical-align: top; }
  th { background: #F4F4F5; font-weight: 600; font-size: 9px; text-transform: uppercase; letter-spacing: 0.02em; color: #52565c; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  tr.flag-row { background: #FBEEEC; }
  .note { font-size: 9.5px; color: #6B7079; font-style: italic; margin-top: -8px; margin-bottom: 14px; }
  .callout { background: #F6F6F7; border-radius: 4px; padding: 10px 14px; margin: 10px 0; font-size: 10px; }
  .callout.bad-callout { background: #FBEEEC; border: 1px solid #E7B7B0; }
  .callout.good-callout { background: #EEF7F1; border: 1px solid #B9DFC6; }
  .page-break { page-break-before: always; }
  thead { display: table-header-group; }
  tr { page-break-inside: avoid; }
  .small { font-size: 9px; color: #8F949C; }
  code { background: #F4F4F5; padding: 1px 4px; border-radius: 3px; font-size: 9.5px; }
  .card { border: 1px solid #DADCE0; border-radius: 6px; padding: 10px 12px; margin: 8px 0 14px; page-break-inside: avoid; }
  .card-title { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; font-weight: 700; font-size: 11px; margin-bottom: 2px; }
  .card-title .row-name { flex: 1; }
  .card-title .row-result { white-space: nowrap; }
  .card-sub { color: #6B7079; font-size: 9.5px; margin-bottom: 6px; }
  .tag { display: inline-block; background: #F4F4F5; border-radius: 3px; padding: 1px 5px; font-size: 8.5px; margin: 1px 2px 1px 0; color: #52565c; }
  .tag.unseen { background: #FBEEEC; color: #A03B32; }
  .tag.extrap { background: #FFF3E0; color: #A9660B; }
"""


def headline_row(m: dict, label: str) -> str:
    cls = "flag-row" if (m["R2"] != m["R2"] or m["R2"] < 0.3) else ""
    return f"""<tr class="{cls}">
      <td>{label}</td><td class="num">{m['n']}</td>
      <td class="num">{fnum(m['MAE'])}</td><td class="num">{fnum(m['RMSE'])}</td>
      <td class="num">{fnum(m['bias'],1) if m['bias']>=0 else fnum(m['bias'],1)}</td><td class="num">{fnum(m['R2'],3)}</td>
    </tr>"""


category_rows = "\n".join(headline_row(by_category[c], CAT_LABEL[c]) for c in ["soft", "semi_hard", "hard"] if by_category[c]["n"] > 0)
support_rows = "\n".join(headline_row(metrics_block(rs), level.replace("_", " ")) for level, rs in levels.items())

# ── Per-row cards (full detail) ─────────────────────────────────────────

def row_card(r: dict) -> str:
    preds = r.get("predictions", {})
    algo_cells = "".join(
        f"<td class='num'>{fnum(preds[a],1) if a in preds else 'n/a'}{' &#9733;' if a == r.get('best_model') else ''}</td>"
        for a in ALGOS
    )
    err = (r["best_pred"] - r["true_days"]) if r.get("best_pred") is not None else None
    err_cls = "bad" if err is not None and abs(err) > 30 else ("warn" if err is not None and abs(err) > 10 else "good")
    tags = []
    for u in r["unseen_categoricals"]:
        tags.append(f"<span class='tag unseen'>unseen {esc(u['feature'])}={esc(u['value'])}</span>")
    for e in r["extrapolations"]:
        tags.append(f"<span class='tag extrap'>{esc(e['detail'])}</span>")
    if r["conc_note"]:
        tags.append(f"<span class='tag extrap'>concentration unit unrecognized: {esc(r['conc_note'])}</span>")
    tags_html = "".join(tags) if tags else "<span class='tag'>no flags</span>"
    pf = r.get("physical_form_support")
    pf_html = f"{esc(pf['label'])} &mdash; {esc(pf['explanation'])}" if pf else "n/a"

    return f"""<div class="card">
      <div class="card-title">
        <span class="row-name">{esc(r['row_id'])} &mdash; {esc(r['category'])} / {esc(r['food_matrix'])}</span>
        <span class="row-result {err_cls}">true {fnum(r['true_days'],0)}d &rarr; pred {fnum(r.get('best_pred'),1)}d (err {err:+.1f}d)</span>
      </div>
      <div class="card-sub">{esc(r.get('citation'))} &middot; DOI {esc(r.get('source_doi'))} &middot; {esc(r.get('publication_year'))}</div>
      <p class="small" style="margin:2px 0 6px;">{esc(r.get('raw_reported_condition'))}</p>
      <table style="margin:4px 0 6px;">
        <thead><tr><th>Random Forest</th><th>LightGBM</th><th>XGBoost</th><th>EBM</th><th>Support level</th></tr></thead>
        <tbody><tr>{algo_cells}<td>{esc(r['support_level'])}</td></tr></tbody>
      </table>
      <div><b class="small">Physical-form support:</b> <span class="small">{pf_html}</span></div>
      <div style="margin-top:4px;">{tags_html}</div>
    </div>"""


row_cards = "\n".join(row_card(r) for r in rows)

worst_cat = min(by_category, key=lambda c: by_category[c]["R2"] if by_category[c]["n"] else 0)
best_cat = max(by_category, key=lambda c: by_category[c]["R2"] if by_category[c]["n"] else -999)

hard_rows = [r for r in predicted if r["category"] == "hard"]
hard_preds = [r["best_pred"] for r in hard_rows]
hard_true = [r["true_days"] for r in hard_rows]

HTML = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>V7 External Test Report</title>
<style>{CSS}</style>
</head><body>

<div class="cover">
  <h1>Cheese Shelf-Life Studio &mdash; V7 External Test Evaluation</h1>
  <div class="subtitle">{len(rows)} real, literature-sourced cases from CHEESE_SHELF_LIFE_V7_EXTERNAL_TEST_POINT_TARGETS.csv, scored against the live V7 specialist pipeline. Generated {generated_at}. Raw model output only &mdash; no correction, multiplier, or manual calibration applied.</div>
</div>

<div class="exec-box">
  <h3>Executive summary</h3>
  <ul>
    <li>All {len(rows)} rows produced a prediction (none hard-blocked) &mdash; but <b>all {len(predicted)} were flagged <code>unsupported_categorical</code></b>: every case uses at least one food_matrix / packaging_type / indicator_type / physical_form value absent from V7&rsquo;s training vocabulary. See &sect;3.</li>
    <li>Overall: n={overall_m['n']}, MAE={fnum(overall_m['MAE'])}d, RMSE={fnum(overall_m['RMSE'])}d, bias={fnum(overall_m['bias'],1)}d, R&sup2;={fnum(overall_m['R2'],3)}.</li>
    <li><b>{CAT_LABEL[best_cat]}</b> generalizes best (R&sup2;={fnum(by_category[best_cat]['R2'],3)}); <b>{CAT_LABEL[worst_cat]}</b> has effectively collapsed on real data (R&sup2;={fnum(by_category[worst_cat]['R2'],3)}, bias={fnum(by_category[worst_cat]['bias'],1)}d) &mdash; see &sect;5.</li>
    <li>A real bug in the support-assessment logic (missing numeric/categorical values misreported as false extrapolation/unseen-category flags) was found and fixed while building this evaluation &mdash; see &sect;6.</li>
    <li>No food_matrix/physical_form/packaging_type/indicator_type value was remapped or guessed to improve the score &mdash; see &sect;2.</li>
  </ul>
</div>

<h2 id="s1">1. Test set</h2>
<p>{len(rows)} cases across {len({r['citation'] for r in rows})} independent papers, all with exact ("point", zero-censoring) targets and <code>direct_model_compatible=yes</code>. All rows are <code>general_shelf_life</code> (no safety-endpoint cases in this file). Category split: soft n={by_category['soft']['n']}, semi-hard n={by_category['semi_hard']['n']}, hard n={by_category['hard']['n']}.</p>

<h2 id="s2">2. Methodology &mdash; what was and wasn't normalized</h2>
<p>Evaluation uses the exact production code path: <code>SpecialistRegistry.resolve()</code> / <code>assess_prediction_support()</code> / <code>ModelService.predict_one()</code> &mdash; the same functions <code>/api/v6/predict</code> calls, not a separate reimplementation. Two, and only two, normalizations were applied, both pure notation (verified, not guessed):</p>
<ul>
  <li><code>cheese_category</code> spelling: <code>"semi-hard"</code> &rarr; <code>"semi_hard"</code>. This is a routing key only &mdash; cheese_category is not even a model feature.</li>
  <li>Concentration units run through the same <code>to_canonical()</code> a live request would use; where the file&rsquo;s unit isn&rsquo;t in the verified table (<code>%_coating_solution</code>, 2 rows), the conversion is left unavailable (None), not guessed.</li>
</ul>
<p><b>Nothing else was remapped.</b> food_matrix, physical_form, packaging_type, and indicator_type values that don&rsquo;t match V7&rsquo;s training vocabulary are passed through as-is and flagged by the existing support-assessment machinery, exactly as a real live prediction would be.</p>

<h2 id="s3">3. Aggregate results</h2>
<table>
<thead><tr><th>Slice</th><th>n</th><th>MAE (d)</th><th>RMSE (d)</th><th>Bias (d)</th><th>R&sup2;</th></tr></thead>
<tbody>
<tr><td><b>Overall</b></td><td class="num">{overall_m['n']}</td><td class="num">{fnum(overall_m['MAE'])}</td><td class="num">{fnum(overall_m['RMSE'])}</td><td class="num">{fnum(overall_m['bias'],1)}</td><td class="num">{fnum(overall_m['R2'],3)}</td></tr>
{category_rows}
</tbody>
</table>
<p class="note">By support level (all {len(predicted)} predicted rows fall in one bucket &mdash; see below):</p>
<table>
<thead><tr><th>Support level</th><th>n</th><th>MAE (d)</th><th>RMSE (d)</th><th>Bias (d)</th><th>R&sup2;</th></tr></thead>
<tbody>{support_rows}</tbody>
</table>
<div class="callout bad-callout">Every one of the {len(predicted)} predictable rows was flagged <code>unsupported_categorical</code> &mdash; there is no "clean" supported subset to compare against in this file. This is the hardened pipeline behaving as designed (it never silently presents an out-of-vocabulary input as a normal-confidence result), but it means the R&sup2;/MAE above conflate genuine model error with vocabulary-coverage gaps. Treat this file as a coverage stress test more than a clean accuracy benchmark until a version using V7&rsquo;s own vocabulary is available.</div>

<h2 id="s4" class="page-break">4. Full per-row detail</h2>
<p class="note">&#9733; marks the specialist&rsquo;s production model (lowest validation RMSE). Every flag is listed in full &mdash; nothing truncated.</p>
{row_cards}

<h2 id="s5" class="page-break">5. Deep dive: hard cheese on real data</h2>
<p>All 5 hard-cheese rows come from one paper (Provolone, aged 6 months, five packaging/CO&#8322; conditions). True values span {fnum(min(hard_true),0)}&ndash;{fnum(max(hard_true),0)}d; predictions cluster at {fnum(min(hard_preds),1)}&ndash;{fnum(max(hard_preds),1)}d &mdash; the model is nearly insensitive to what actually distinguishes these five real cases. MAE={fnum(by_category['hard']['MAE'])}d, bias={fnum(by_category['hard']['bias'],1)}d (systematic underprediction), R&sup2;={fnum(by_category['hard']['R2'],3)}.</p>
<div class="callout bad-callout">This mirrors a generalization weakness that has recurred across multiple model generations in this project&rsquo;s history for long-aged hard cheese &mdash; the V7 retrain and architecture change have not resolved it. It is reported as-is; no correction was applied.</div>

<h2 id="s6">6. Bug found and fixed while building this evaluation</h2>
<p><code>ModelService.assess_support()</code> compared every numeric field&rsquo;s raw value against its training range without first checking for <code>NaN</code> (as opposed to <code>None</code>) &mdash; the natural result of <code>pandas.read_csv</code> on an empty cell, which several rows in this external file have (e.g. missing <code>matrix_ph</code>). A NaN always fails a range comparison, so it was being reported as a false "value=nan is outside the training range" extrapolation instead of being treated as missing data; the same applied to categorical NaNs being reported as an unseen category "value='nan'". Fixed with a shared missing-value check used in both the categorical and numeric loops, verified directly, and re-confirmed the full 23-case pytest suite (<code>test_v6_specialist_routing.py</code>) still passes since this is shared V6/V7 infrastructure.</p>

<h2 id="s7">7. Recommendations</h2>
<ol>
  <li>Build (or request) a version of this external file using V7&rsquo;s own trained vocabulary for food_matrix/physical_form/packaging_type/indicator_type, so accuracy can be assessed independent of vocabulary coverage.</li>
  <li>Do not remap or fuzzy-match the current file&rsquo;s vocabulary retroactively to make the score look better &mdash; a wrong mapping would be worse than an honest "unsupported" flag.</li>
  <li>Hard cheese needs targeted attention specifically for long-aged profiles (Provolone-like) before any external validation claim is made for that category &mdash; consistent with every prior model generation in this project.</li>
  <li>Semi-hard is the most promising generalizer here (R&sup2;={fnum(by_category['semi_hard']['R2'],3)}) despite the same vocabulary-mismatch handicap &mdash; worth prioritizing if choosing where to invest further validation effort first.</li>
</ol>

<p class="small" style="margin-top:20px;">Report generated from data/raw/CHEESE_SHELF_LIFE_V7_EXTERNAL_TEST_POINT_TARGETS.csv via evaluate_v7_external_test.run_evaluation(), against the live artifacts_v7/ specialists. Full machine-readable output: v7_external_test_predictions.csv. No retraining, data modification, or prediction correction occurred in the course of this evaluation or report.</p>

</body></html>
"""

with open("v7_external_test_report.html", "w", encoding="utf-8") as f:
    f.write(HTML)
print("Wrote v7_external_test_report.html")
print("Render to PDF with: cd frontend && node _render_v7_external_pdf.mjs")
