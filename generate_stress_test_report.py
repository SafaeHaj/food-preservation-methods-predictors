#!/usr/bin/env python
"""
Generates a complete, detailed HTML report (later rendered to PDF) covering
every measure and every row of the CHEESE_319_REAL_EXTERNAL_STRESS_TEST_CASES
evaluation, for all 4 live models, comparing three model generations (v1, v3,
v4). Read-only: reads stress_test_319_predictions.csv (already computed by
evaluate_319_stress_test.py) plus the two prior versions' backed-up copies,
and the training workbooks for root-cause comparison; writes only the report
HTML.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODELS = [
    ("pred_random_forest", "Random Forest"),
    ("pred_lightgbm", "LightGBM"),
    ("pred_xgboost", "XGBoost"),
    ("pred_ebm", "Explainable Boosting Machine"),
]
BEST_MODEL_COL = "pred_xgboost"
BEST_MODEL_LABEL = "XGBoost"
TARGET = "shelf_life_days"
LOWER_BOUND_TIERS = {"B_LOWER_BOUND_REAL", "C_STUDY_HORIZON_REAL", "C_SAFETY_EVENT_REAL"}
TIER_ORDER = ["A_STRICT_REAL", "A_RANGE_REAL", "B_OVERALL_REAL", "B_LOWER_BOUND_REAL", "C_STUDY_HORIZON_REAL", "C_SAFETY_EVENT_REAL"]
TIER_DESCRIPTIONS = {
    "A_STRICT_REAL": "Exact reported value from the paper. Highest confidence.",
    "A_RANGE_REAL": "Paper reported a range rather than a single value.",
    "B_OVERALL_REAL": "Overall / nominal shelf-life claim stated in the paper.",
    "B_LOWER_BOUND_REAL": "Paper reports “no spoilage by day X” — true value is at least X.",
    "C_STUDY_HORIZON_REAL": "Value is bounded by how long the study ran (looser lower bound).",
    "C_SAFETY_EVENT_REAL": "Value tied to a specific pathogen/safety endpoint, not general spoilage.",
}

V1_BACKUP_DIR = "model_versions/v1_restored_baseline_2026-08-18_141539"
V3_BACKUP_DIR = "model_versions/v3_recalibrated_2026-08-19_124027"

df = pd.read_csv("stress_test_319_predictions.csv")            # current = v4
df_v1 = pd.read_csv(f"{V1_BACKUP_DIR}/stress_test_319_predictions.csv")
df_v3 = pd.read_csv(f"{V3_BACKUP_DIR}/stress_test_319_predictions.csv")
y_true = df[TARGET].to_numpy(dtype=float)
y_true_v1 = df_v1[TARGET].to_numpy(dtype=float)
y_true_v3 = df_v3[TARGET].to_numpy(dtype=float)


def metrics(mask, pred_col, frame=None, truth=None) -> dict:
    frame = df if frame is None else frame
    truth = y_true if truth is None else truth
    yt = truth[mask]
    yp = frame.loc[mask, pred_col].to_numpy(dtype=float)
    n = len(yt)
    if n == 0:
        return dict(n=0, MAE=np.nan, RMSE=np.nan, R2=np.nan, MAPE=np.nan, bias=np.nan, medAE=np.nan)
    err = yp - yt
    ss_res = (err ** 2).sum()
    ss_tot = ((yt - yt.mean()) ** 2).sum() if n > 1 else np.nan
    r2 = 1 - ss_res / ss_tot if ss_tot and ss_tot > 0 else np.nan
    pct = np.where(yt > 0, np.abs(err) / yt * 100, np.nan)
    return dict(n=n, MAE=np.abs(err).mean(), RMSE=np.sqrt((err ** 2).mean()), R2=r2,
                MAPE=np.nanmean(pct), bias=err.mean(), medAE=np.median(np.abs(err)))


def m_v1(mask, pred_col="pred_xgboost"):
    return metrics(mask, pred_col, frame=df_v1, truth=y_true_v1)


def m_v3(mask, pred_col="pred_xgboost"):
    return metrics(mask, pred_col, frame=df_v3, truth=y_true_v3)


def m_v4(mask, pred_col="pred_xgboost"):
    return metrics(mask, pred_col, frame=df, truth=y_true)


def fnum(v, dp=2, suffix=""):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.{dp}f}{suffix}"


def _signed(v, dp=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{'+' if v >= 0 else ''}{v:.{dp}f}"


def compare3_row(label, mask_v1, mask_v3, mask_v4):
    a, b, c = m_v1(mask_v1), m_v3(mask_v3), m_v4(mask_v4)
    d34 = c["R2"] - b["R2"] if (c["R2"] == c["R2"] and b["R2"] == b["R2"]) else np.nan
    arrow = "better" if (d34 == d34 and d34 > 0.02) else ("worse" if (d34 == d34 and d34 < -0.02) else "flat")
    return (f"<tr><td>{label}</td>"
            f"<td class='num'>{fnum(a['R2'],3)}</td><td class='num'>{fnum(b['R2'],3)}</td><td class='num'>{fnum(c['R2'],3)}</td>"
            f"<td class='num'>{_signed(a['bias'])}d</td><td class='num'>{_signed(b['bias'])}d</td><td class='num'>{_signed(c['bias'])}d</td>"
            f"<td class='{arrow}'>{'▲ improved' if arrow=='better' else ('▼ regressed' if arrow=='worse' else '≈ flat')}</td></tr>")


def metrics_row_html(label, m, highlight=False):
    cls = ' class="best-row"' if highlight else ""
    return (f"<tr{cls}><td>{label}</td><td class='num'>{m['n']}</td>"
            f"<td class='num'>{fnum(m['MAE'],2,'d')}</td><td class='num'>{fnum(m['RMSE'],2,'d')}</td>"
            f"<td class='num'>{fnum(m['R2'],3)}</td><td class='num'>{fnum(m['MAPE'],1,'%')}</td>"
            f"<td class='num'>{_signed(m['bias'],2)}d</td>"
            f"<td class='num'>{fnum(m['medAE'],2,'d')}</td></tr>")


def metrics_table(title, rows_html, note=""):
    return f"""
    <table class="metrics">
      <caption>{title}</caption>
      <thead><tr><th>Model / Group</th><th>n</th><th>MAE</th><th>RMSE</th><th>R²</th><th>MAPE</th><th>Bias</th><th>Median AE</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    {f'<p class="note">{note}</p>' if note else ''}
    """


# ── Overall, all models (v4) ───────────────────────────────────────────
overall_rows = "".join(
    metrics_row_html(label, metrics(np.full(len(df), True), col), highlight=(col == BEST_MODEL_COL))
    for col, label in sorted(MODELS, key=lambda kv: metrics(np.full(len(df), True), kv[0])["MAE"])
)

# ── By quality tier, all models (v4) ──────────────────────────────────────────
tier_sections = []
for tier in TIER_ORDER:
    mask = (df["quality_tier"] == tier).to_numpy()
    rows_html = "".join(
        metrics_row_html(label, metrics(mask, col), highlight=(col == BEST_MODEL_COL))
        for col, label in MODELS
    )
    tier_sections.append(metrics_table(f"{tier}  (n={mask.sum()})", rows_html, TIER_DESCRIPTIONS[tier]))

# ── A_STRICT_REAL emphasis (v4) ────────────────────────────────────────────
strict_mask = (df["quality_tier"] == "A_STRICT_REAL").to_numpy()
strict_rows = "".join(
    metrics_row_html(label, metrics(strict_mask, col), highlight=(col == BEST_MODEL_COL))
    for col, label in sorted(MODELS, key=lambda kv: metrics(strict_mask, kv[0])["MAE"])
)
m_strict_lgb_v4 = metrics(strict_mask, "pred_lightgbm")

# ── By cheese category, all models (v4) ────────────────────────────────────────
cat_sections = []
for cat in ["soft", "semi_hard", "hard"]:
    mask = (df["cheese_category"] == cat).to_numpy()
    rows_html = "".join(
        metrics_row_html(label, metrics(mask, col), highlight=(col == BEST_MODEL_COL))
        for col, label in MODELS
    )
    cat_sections.append(metrics_table(f"Cheese category: {cat}  (n={mask.sum()})", rows_html))

# ── By control vs treatment (v4) ────────────────────────────────────────────
ctl_sections = []
for ctl, label in [(1, "Control (untreated)"), (0, "Treatment")]:
    mask = (df["is_control"] == ctl).to_numpy()
    rows_html = "".join(
        metrics_row_html(mlabel, metrics(mask, col), highlight=(col == BEST_MODEL_COL))
        for col, mlabel in MODELS
    )
    ctl_sections.append(metrics_table(f"{label}  (n={mask.sum()})", rows_html))

# ── In-range vs out-of-range (root cause: rule out extrapolation, v4) ────────────
schema = json.load(open("artifacts/schema.json"))
ranges = schema["numeric_ranges"]
in_range = pd.Series(True, index=df.index)
for col in ["storage_temperature_c", "headspace_oxygen_pct", "headspace_co2_pct", "headspace_n2_pct",
            "primary_concentration", "matrix_ph", "matrix_water_activity"]:
    if col in ranges:
        lo, hi = ranges[col]["min"], ranges[col]["max"]
        in_range &= df[col].between(lo, hi)
in_range_np = in_range.to_numpy()
m_in = metrics(in_range_np, BEST_MODEL_COL)
m_out = metrics(~in_range_np, BEST_MODEL_COL)
m_hard_in = metrics(in_range_np & (df["cheese_category"] == "hard").to_numpy(), BEST_MODEL_COL)

# ── Lower-bound compliance, v1 / v3 / v4 ───────────────────────────────────
lb_mask = df["quality_tier"].isin(LOWER_BOUND_TIERS).to_numpy()
lb_meets = (df.loc[lb_mask, BEST_MODEL_COL].to_numpy() >= y_true[lb_mask])
lb_pct = lb_meets.mean() * 100
lb_under_n = (~lb_meets).sum()

lb_mask_v1 = df_v1["quality_tier"].isin(LOWER_BOUND_TIERS).to_numpy()
lb_meets_v1 = (df_v1.loc[lb_mask_v1, BEST_MODEL_COL].to_numpy() >= y_true_v1[lb_mask_v1])
lb_pct_v1 = lb_meets_v1.mean() * 100

lb_mask_v3 = df_v3["quality_tier"].isin(LOWER_BOUND_TIERS).to_numpy()
lb_meets_v3 = (df_v3.loc[lb_mask_v3, BEST_MODEL_COL].to_numpy() >= y_true_v3[lb_mask_v3])
lb_pct_v3 = lb_meets_v3.mean() * 100

# ── Root-cause: Parmigiano + Cheddar synthetic-vs-real, v1 / v3 / v4 labels ────────────
train_v1 = pd.read_excel("data/raw/CHEESE_SHELF_LIFE_REVISED_READY_TO_TRAIN.xlsx", sheet_name="training_data")
train_v3 = pd.read_excel("data/raw/CHEESE_SHELF_LIFE_RECALIBRATED_V3_READY_TO_TRAIN.xlsx", sheet_name="training_data")
train_v4 = pd.read_excel("data/raw/CHEESE_SHELF_LIFE_TARGETED_V4_READY_TO_TRAIN.xlsx", sheet_name="training_data")
test_raw = pd.read_excel("data/raw/CHEESE_319_REAL_EXTERNAL_STRESS_TEST_CASES.xlsx", sheet_name="External_Test_Cases")
parm = test_raw[test_raw["food_matrix"] == "parmigiano reggiano"].iloc[0]


def matching_hard(train_df):
    return train_df[
        (train_df["cheese_category"] == "hard") &
        (train_df["matrix_ripening_days"].between(parm["matrix_ripening_days"] * 0.7, parm["matrix_ripening_days"] * 1.3)) &
        (train_df["matrix_moisture_pct"].between(parm["matrix_moisture_pct"] * 0.8, parm["matrix_moisture_pct"] * 1.2)) &
        (train_df["is_control"] == 1)
    ]


similar_parm_v1 = matching_hard(train_v1)
similar_parm_v3 = matching_hard(train_v3)
similar_parm_v4 = matching_hard(train_v4)
parm_ratio_v1 = similar_parm_v1["shelf_life_days"].median() / parm["shelf_life_days"]
parm_ratio_v3 = similar_parm_v3["shelf_life_days"].median() / parm["shelf_life_days"]
parm_ratio_v4 = similar_parm_v4["shelf_life_days"].median() / parm["shelf_life_days"]
parm_actual_v4_mean = df[df["food_matrix"] == "parmigiano reggiano"]["pred_xgboost"].mean()
parm_actual_v3_mean = df_v3[df_v3["food_matrix"] == "parmigiano reggiano"]["pred_xgboost"].mean()

cheddar_real = test_raw[(test_raw["food_matrix"] == "cheddar") & (test_raw["is_control"] == 1)].iloc[0]


def matching_cheddar(train_df):
    return train_df[
        (train_df["food_matrix"] == "cheddar") &
        (train_df["matrix_ripening_days"].between(max(0, cheddar_real["matrix_ripening_days"] * 0.6), cheddar_real["matrix_ripening_days"] * 1.4 + 10)) &
        (train_df["is_control"] == 1)
    ]


similar_cheddar_v1 = matching_cheddar(train_v1)
similar_cheddar_v3 = matching_cheddar(train_v3)
similar_cheddar_v4 = matching_cheddar(train_v4)
cheddar_ratio_v1 = similar_cheddar_v1["shelf_life_days"].median() / cheddar_real["shelf_life_days"]
cheddar_ratio_v3 = similar_cheddar_v3["shelf_life_days"].median() / cheddar_real["shelf_life_days"]
cheddar_ratio_v4 = similar_cheddar_v4["shelf_life_days"].median() / cheddar_real["shelf_life_days"]

m_hard_v1 = m_v1((df_v1["cheese_category"] == "hard").to_numpy())
m_hard_v3 = m_v3((df_v3["cheese_category"] == "hard").to_numpy())
m_hard_v4 = m_v4((df["cheese_category"] == "hard").to_numpy())

# ── Feta / A_STRICT_REAL: v1 → v3 (broke) → v4 (fixed) ────────────────────────────
feta_v1 = df_v1[(df_v1["food_matrix"] == "feta") & (df_v1["quality_tier"] == "A_STRICT_REAL")][["row_id", TARGET, "pred_xgboost"]].sort_values("row_id")
feta_v3 = df_v3[(df_v3["food_matrix"] == "feta") & (df_v3["quality_tier"] == "A_STRICT_REAL")][["row_id", "pred_xgboost"]].sort_values("row_id")
feta_v4 = df[(df["food_matrix"] == "feta") & (df["quality_tier"] == "A_STRICT_REAL")][["row_id", "pred_xgboost"]].sort_values("row_id")
feta_strict_mask = strict_mask & (df["food_matrix"] == "feta").to_numpy()
non_feta_strict_mask = strict_mask & ~(df["food_matrix"] == "feta").to_numpy()
m_strict_nonfeta_v4 = metrics(non_feta_strict_mask, "pred_xgboost")
m_strict_feta_v4 = metrics(feta_strict_mask, "pred_xgboost")


def _err(true, pred):
    e = pred - true
    return f"{'+' if e >= 0 else ''}{e:.1f}"


feta_rows_html = "".join(
    f"<tr><td>{r1.row_id}</td><td class='num'>{fnum(r1[TARGET],1)}</td>"
    f"<td class='num'>{fnum(r1['pred_xgboost'],1)}</td><td class='num'>{_err(r1[TARGET], r1['pred_xgboost'])}</td>"
    f"<td class='num'>{fnum(r3['pred_xgboost'],1)}</td><td class='num'>{_err(r1[TARGET], r3['pred_xgboost'])}</td>"
    f"<td class='num'>{fnum(r4['pred_xgboost'],1)}</td><td class='num'>{_err(r1[TARGET], r4['pred_xgboost'])}</td></tr>"
    for (_, r1), (_, r3), (_, r4) in zip(feta_v1.iterrows(), feta_v3.iterrows(), feta_v4.iterrows())
)

# ── NEW v4 regression: semi-hard cheese label inflation (processed cheese / kashar / gouda) ────
SEMI_HARD_CHECK = ["processed cheese", "kashar", "gouda"]
semihard_label_rows = []
for fm in SEMI_HARD_CHECK:
    sub3 = train_v3[train_v3["food_matrix"] == fm]
    sub4 = train_v4[train_v4["food_matrix"] == fm]
    semihard_label_rows.append((fm, len(sub3), sub3["shelf_life_days"].median(), len(sub4), sub4["shelf_life_days"].median()))
semihard_label_html = "".join(
    f"<tr><td>{fm}</td><td class='num'>{n3}</td><td class='num'>{fnum(med3,1)}d</td>"
    f"<td class='num'>{n4}</td><td class='num'>{fnum(med4,1)}d</td>"
    f"<td class='num {'worse' if med4>med3 else 'better'}'>{'+' if med4>=med3 else ''}{fnum((med4/med3-1)*100,0)}%</td></tr>"
    for fm, n3, med3, n4, med4 in semihard_label_rows
)

pc_real = df[(df["food_matrix"] == "processed cheese") & (df["quality_tier"] == "C_SAFETY_EVENT_REAL")][
    ["row_id", TARGET, "storage_temperature_c", "indicator_type", "is_control", "pred_xgboost"]
].copy()
pc_real_v3 = df_v3.set_index("row_id")["pred_xgboost"]
pc_real["pred_v3"] = pc_real["row_id"].map(pc_real_v3)
pc_rows_html = "".join(
    f"<tr><td>{r.row_id}</td><td class='num'>{fnum(r[TARGET],1)}</td><td class='num'>{fnum(r.storage_temperature_c,0)}°C</td>"
    f"<td>{r.indicator_type}</td><td class='num'>{fnum(r.pred_v3,1)}</td><td class='num'>{fnum(r.pred_xgboost,1)}</td></tr>"
    for _, r in pc_real.iterrows()
)

m_semihard_v1 = m_v1((df_v1["cheese_category"] == "semi_hard").to_numpy())
m_semihard_v3 = m_v3((df_v3["cheese_category"] == "semi_hard").to_numpy())
m_semihard_v4 = m_v4((df["cheese_category"] == "semi_hard").to_numpy())
m_safety_v1 = m_v1((df_v1["quality_tier"] == "C_SAFETY_EVENT_REAL").to_numpy())
m_safety_v3 = m_v3((df_v3["quality_tier"] == "C_SAFETY_EVENT_REAL").to_numpy())
m_safety_v4 = m_v4((df["quality_tier"] == "C_SAFETY_EVENT_REAL").to_numpy())

m_soft_v4 = m_v4((df["cheese_category"] == "soft").to_numpy())
m_ebm_strict_v4 = metrics(strict_mask, "pred_ebm")

# ── Per-paper breakdown, all papers (v4) ──────────────────────────────────────
paper_rows = []
for doi, g in df.groupby("source_rule_id"):
    mask = (df["source_rule_id"] == doi).to_numpy()
    m = metrics(mask, BEST_MODEL_COL)
    paper_rows.append((doi, m))
paper_rows.sort(key=lambda kv: kv[1]["MAE"], reverse=True)
paper_table_rows = "".join(
    f"<tr><td class='doi'>{doi}</td><td class='num'>{m['n']}</td><td class='num'>{fnum(m['MAE'])}</td>"
    f"<td class='num'>{fnum(m['R2'],3)}</td><td class='num'>{_signed(m['bias'])}</td></tr>"
    for doi, m in paper_rows
)
worst_paper_doi, worst_paper_m = paper_rows[0]
worst_paper_pct_of_total = worst_paper_m["n"] / len(df) * 100

dominant_doi, dominant_m = max(paper_rows, key=lambda kv: kv[1]["n"] * kv[1]["MAE"] ** 2)
dominant_pct_of_total = dominant_m["n"] / len(df) * 100

# ── Worst 30 (v4) ────────────────────────────────────────────────────
df["signed_err"] = df[BEST_MODEL_COL] - y_true
worst = df.reindex(df["abs_err"].sort_values(ascending=False).index).head(30)
worst_rows = "".join(
    f"<tr><td>{r.row_id}</td><td>{r.food_matrix}</td><td>{r.cheese_category}</td><td class='tier'>{r.quality_tier}</td>"
    f"<td class='num'>{fnum(r[TARGET],1)}</td><td class='num'>{fnum(r[BEST_MODEL_COL],1)}</td>"
    f"<td class='num {'over' if r.signed_err>=0 else 'under'}'>{_err(0, r.signed_err)}</td></tr>"
    for _, r in worst.iterrows()
)

# ── Full per-row appendix, ALL 319 rows, ALL 4 models (v4) ────────────────────
df_sorted = df.sort_values(["cheese_category", "quality_tier", "food_matrix", "row_id"])
full_rows = []
for _, r in df_sorted.iterrows():
    cells = [
        f"<td>{r.row_id}</td>", f"<td>{r.food_matrix}</td>", f"<td>{r.cheese_category}</td>",
        f"<td class='tier'>{r.quality_tier}</td>", f"<td class='num'>{fnum(r[TARGET],1)}</td>",
    ]
    for col, _label in MODELS:
        err = r[col] - r[TARGET]
        cls = "over" if err >= 0 else "under"
        cells.append(f"<td class='num'>{fnum(r[col],1)}</td><td class='num {cls}'>{_err(0, err)}</td>")
    full_rows.append(f"<tr>{''.join(cells)}</tr>")
full_table_rows = "".join(full_rows)

# ── v1 / v3 / v4 headline comparison table ──────────────────────────────────────
mask_all_v1 = np.full(len(df_v1), True)
mask_all_v3 = np.full(len(df_v3), True)
mask_all_v4 = np.full(len(df), True)
comparison_rows = "".join([
    compare3_row("Overall (pooled, all 319, all tiers)", mask_all_v1, mask_all_v3, mask_all_v4),
    compare3_row("A_STRICT_REAL (n=27)",
                 (df_v1["quality_tier"] == "A_STRICT_REAL").to_numpy(),
                 (df_v3["quality_tier"] == "A_STRICT_REAL").to_numpy(),
                 (df["quality_tier"] == "A_STRICT_REAL").to_numpy()),
    compare3_row("C_STUDY_HORIZON_REAL (n=159, largest tier)",
                 (df_v1["quality_tier"] == "C_STUDY_HORIZON_REAL").to_numpy(),
                 (df_v3["quality_tier"] == "C_STUDY_HORIZON_REAL").to_numpy(),
                 (df["quality_tier"] == "C_STUDY_HORIZON_REAL").to_numpy()),
    compare3_row("C_SAFETY_EVENT_REAL (n=52)",
                 (df_v1["quality_tier"] == "C_SAFETY_EVENT_REAL").to_numpy(),
                 (df_v3["quality_tier"] == "C_SAFETY_EVENT_REAL").to_numpy(),
                 (df["quality_tier"] == "C_SAFETY_EVENT_REAL").to_numpy()),
    compare3_row("Hard cheese (n=35)",
                 (df_v1["cheese_category"] == "hard").to_numpy(),
                 (df_v3["cheese_category"] == "hard").to_numpy(),
                 (df["cheese_category"] == "hard").to_numpy()),
    compare3_row("Semi-hard cheese (n=114)",
                 (df_v1["cheese_category"] == "semi_hard").to_numpy(),
                 (df_v3["cheese_category"] == "semi_hard").to_numpy(),
                 (df["cheese_category"] == "semi_hard").to_numpy()),
    compare3_row("Soft cheese (n=170)",
                 (df_v1["cheese_category"] == "soft").to_numpy(),
                 (df_v3["cheese_category"] == "soft").to_numpy(),
                 (df["cheese_category"] == "soft").to_numpy()),
])

n_total = len(df)
generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

HTML = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Results Report</title>
<style>
  @page {{ size: A4; margin: 16mm 14mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "Segoe UI", Arial, sans-serif; color: #16181c; font-size: 10.5px; line-height: 1.5; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  h2 {{ font-size: 15px; margin: 26px 0 8px; padding-bottom: 4px; border-bottom: 2px solid #7A1B2E; page-break-after: avoid; }}
  h3 {{ font-size: 12.5px; margin: 16px 0 6px; page-break-after: avoid; }}
  p {{ margin: 6px 0; }}
  .subtitle {{ color: #6B7079; font-size: 11px; margin-bottom: 18px; }}
  .cover {{ border-bottom: 3px solid #7A1B2E; padding-bottom: 14px; margin-bottom: 6px; }}
  .exec-box {{ background: #FBF3F4; border: 1px solid #E9C7CC; border-left: 4px solid #7A1B2E; border-radius: 4px; padding: 12px 16px; margin: 10px 0 20px; }}
  .exec-box h3 {{ margin-top: 0; color: #7A1B2E; }}
  .exec-box ul {{ margin: 4px 0; padding-left: 18px; }}
  .good {{ color: #157F52; font-weight: 600; }}
  .bad {{ color: #C0362C; font-weight: 600; }}
  table {{ border-collapse: collapse; width: 100%; margin: 6px 0 14px; page-break-inside: auto; }}
  table.metrics {{ width: auto; min-width: 70%; }}
  caption {{ text-align: left; font-weight: 600; font-size: 11px; margin-bottom: 4px; caption-side: top; }}
  th, td {{ border: 1px solid #DADCE0; padding: 3px 6px; text-align: left; }}
  th {{ background: #F4F4F5; font-weight: 600; font-size: 9.5px; text-transform: uppercase; letter-spacing: 0.02em; color: #52565c; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  tr.best-row {{ background: #FBF3F4; font-weight: 600; }}
  td.over {{ color: #C0362C; }}
  td.under {{ color: #2E5FA3; }}
  td.better {{ color: #157F52; font-weight: 600; }}
  td.worse {{ color: #C0362C; font-weight: 600; }}
  td.flat {{ color: #8F949C; }}
  td.tier {{ font-size: 9px; color: #6B7079; }}
  td.doi {{ font-size: 8.5px; word-break: break-all; }}
  .note {{ font-size: 9.5px; color: #6B7079; font-style: italic; margin-top: -8px; margin-bottom: 14px; }}
  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0 20px; }}
  .callout {{ background: #F6F6F7; border-radius: 4px; padding: 10px 14px; margin: 10px 0; font-size: 10px; }}
  .callout.proof {{ background: #FFF7E8; border: 1px solid #EAD9AE; }}
  .callout.bad-callout {{ background: #FBEEEC; border: 1px solid #E7B7B0; }}
  .callout.good-callout {{ background: #EEF7F1; border: 1px solid #B9DFC6; }}
  .page-break {{ page-break-before: always; }}
  .issues li {{ margin-bottom: 8px; }}
  .issues b {{ color: #7A1B2E; }}
  thead {{ display: table-header-group; }}
  tr {{ page-break-inside: avoid; }}
  .toc {{ columns: 2; margin: 14px 0 24px; font-size: 10.5px; }}
  .toc a {{ color: #16181c; text-decoration: none; }}
  .small {{ font-size: 9px; color: #8F949C; }}
</style>
</head>
<body>

<div class="cover">
  <h1>Shelf-Life Prediction Models &mdash; v4 Targeted Recalibration Results Report</h1>
  <p class="subtitle">CHEESE_SHELF_LIFE_TARGETED_V4_READY_TO_TRAIN.xlsx (35,650 rows) retrained from scratch, tested against the same unmodified CHEESE_319_REAL_EXTERNAL_STRESS_TEST_CASES.xlsx &middot; 319 cases &middot; 34 real papers (DOI-traced) &middot; generated {generated_at}</p>
</div>

<div class="exec-box">
  <h3>Executive summary &mdash; v4 vs. v3 vs. v1, on the identical 319-case test set</h3>
  <ul>
    <li><b>V4 fixed the one specific problem flagged in the v3 report.</b> A_STRICT_REAL (n=27, the tier singled out for R&sup2;): <span class="bad">R&sup2;=-1.42 (v3)</span> &rarr; <span class="good">R&sup2;={fnum(metrics(strict_mask,'pred_xgboost')['R2'],2)} (v4, XGBoost)</span>, or <span class="good">R&sup2;={fnum(m_strict_lgb_v4['R2'],2)} with LightGBM</span> (v4's new default best model) &mdash; essentially back to v1's original quality. The 2 feta rows that broke this tier in v3 are now predicted accurately again.</li>
    <li><b>But v4 is not a net improvement &mdash; it traded one problem for two others.</b> Pooled R&sup2; across all 319 rows fell: <span class="good">0.445 (v3)</span> &rarr; <span class="bad">{fnum(metrics(mask_all_v4,'pred_xgboost')['R2'],3)} (v4)</span>.</li>
    <li><b>Semi-hard cheese collapsed</b>: R&sup2; {fnum(m_semihard_v3['R2'],3)} (v3, genuinely good) &rarr; <span class="bad">{fnum(m_semihard_v4['R2'],3)} (v4)</span>, bias +{fnum(m_semihard_v3['bias'],1)}d &rarr; <span class="bad">+{fnum(m_semihard_v4['bias'],1)}d</span>. Root-caused below (&sect;8.4) to the v4 training labels for processed cheese, kashar, and gouda being substantially <i>inflated</i> versus v3.</li>
    <li><b>C_SAFETY_EVENT_REAL got substantially worse</b>: R&sup2; {fnum(m_safety_v3['R2'],2)} (v3) &rarr; <span class="bad">{fnum(m_safety_v4['R2'],2)} (v4)</span> &mdash; same root cause, since most of these rows are processed-cheese pathogen-challenge cases.</li>
    <li>Hard cheese continued improving (R&sup2; {fnum(m_hard_v3['R2'],2)} &rarr; {fnum(m_hard_v4['R2'],2)}), and lower-bound compliance held roughly flat ({fnum(lb_pct_v3,0)}% &rarr; {fnum(lb_pct,0)}%).</li>
  </ul>
</div>

<h2 id="toc">Contents</h2>
<div class="toc">
  <a href="#methodology">1. Methodology</a><br>
  <a href="#comparison">2. v1 vs. v3 vs. v4 headline comparison</a><br>
  <a href="#overall">3. Overall results, all models (v4)</a><br>
  <a href="#tiers">4. Results by confidence tier (v4)</a><br>
  <a href="#strict">5. A_STRICT_REAL deep dive &mdash; the fix</a><br>
  <a href="#category">6. Results by cheese category (v4)</a><br>
  <a href="#control">7. Control vs. treatment (v4)</a><br>
  <a href="#rootcause">8. Root cause analysis</a><br>
  <a href="#lowerbound">9. Lower-bound compliance</a><br>
  <a href="#papers">10. Per-paper breakdown (34 papers)</a><br>
  <a href="#worst">11. Worst 30 predictions (v4)</a><br>
  <a href="#issues">12. Issues identified (v4 state)</a><br>
  <a href="#recommendations">13. Recommendations</a><br>
  <a href="#appendix">14. Appendix: full per-row results, v4 (all 319 rows)</a>
</div>

<h2 id="methodology">1. Methodology</h2>
<p>319 real-condition cases traced to 34 distinct published papers (<code>source_rule_id</code> holds the actual DOI/PubMed link for each). <code>data_origin = external_literature_real_condition</code> and <code>training_weight = 0</code> for every row &mdash; entirely disjoint from the training set, never used in fitting. Each row's <code>quality_flag</code> prefix is a confidence/comparison-semantics tier:</p>
<table class="metrics">
<thead><tr><th>Tier</th><th>n</th><th>Meaning</th></tr></thead>
<tbody>
{"".join(f"<tr><td>{t}</td><td class='num'>{(df['quality_tier']==t).sum()}</td><td>{TIER_DESCRIPTIONS[t]}</td></tr>" for t in TIER_ORDER)}
</tbody>
</table>
<p>All 4 live production models (Random Forest, LightGBM, XGBoost, Explainable Boosting Machine) were evaluated identically via <code>ModelService.predict_one()</code> &mdash; the exact same code path the deployed app uses, with zero retraining. Metrics: MAE (mean absolute error), RMSE, R&sup2; (coefficient of determination against the reported/imputed true value), MAPE, bias (mean signed error &mdash; positive means overprediction), and median absolute error (robust to outliers).</p>
<p>This report compares three model generations against the identical, unmodified 319-row file: <b>v1</b> (original training data, backed up under <code>{V1_BACKUP_DIR}/</code>), <b>v3</b> (broad recalibration of hard/semi-hard labels, 48,240 rows, backed up under <code>{V3_BACKUP_DIR}/</code>), and <b>v4</b> (current live models, a more targeted recalibration on 35,650 rows &mdash; ~26,050 rows retained from the original v1-era base plus ~9,600 rows newly added/recalibrated under <code>synthetic_independent_literature_calibrated_v4</code> / <code>synthetic_recalibrated_v4</code>). All single-version sections below (3 onward) reflect v4, the current live app; &sect;2 puts all three side by side. XGBoost is used as the comparison model throughout for architecture-controlled consistency across versions, even though v4's own best-by-validation model is now LightGBM (noted where relevant).</p>

<h2 id="comparison">2. v1 vs. v3 vs. v4 headline comparison (XGBoost, identical 319 rows)</h2>
<p>Same evaluation script, same test file, unmodified, run three times against three different sets of trained artifacts. ▲/▼ reflect the v3&rarr;v4 change in R&sup2; beyond &plusmn;0.02; smaller shifts are marked ≈ flat.</p>
<table class="metrics">
<thead><tr><th>Segment</th><th>R&sup2; (v1)</th><th>R&sup2; (v3)</th><th>R&sup2; (v4)</th><th>Bias (v1)</th><th>Bias (v3)</th><th>Bias (v4)</th><th>v3&rarr;v4</th></tr></thead>
<tbody>{comparison_rows}</tbody>
</table>
<div class="callout"><b>Reading this table honestly:</b> v4 is a genuine win on exactly one thing &mdash; A_STRICT_REAL, the tier this project has repeatedly been asked to report R&sup2; on. Everywhere else the picture is mixed-to-worse: hard cheese kept improving, but semi-hard cheese and C_SAFETY_EVENT_REAL both regressed sharply, and pooled R&sup2; fell back toward v1-era territory. This is not "v4 is better" or "v4 is worse" than v3 &mdash; it is a different, narrower trade-off, root-caused in &sect;8.</div>

<h2 id="overall">3. Overall results &mdash; all 319 rows, all tiers pooled, every model (v4)</h2>
{metrics_table("All models, ranked by MAE", overall_rows, "The current app-selected best model is LightGBM (lowest validation RMSE on the v4 split, a change from XGBoost in v1/v3) — not necessarily the best on this real test set; comparison tables in this report keep using XGBoost throughout for cross-version consistency.")}

<h2 id="tiers">4. Results by confidence tier &mdash; every model (v4)</h2>
<p class="note">R&sup2; on tiers with a narrow true-value range (e.g. A_RANGE_REAL, n=4) is statistically unstable by construction &mdash; small denominators make R&sup2; swing wildly. MAE/bias are more reliable for those tiers.</p>
{''.join(tier_sections)}

<h2 id="strict">5. A_STRICT_REAL deep dive (n=27) &mdash; the tier requested for R&sup2;, and the one v4 fixed</h2>
<p>These are the 27 rows where a paper reported an exact shelf-life value with no ambiguity, no bound, no imputation of the outcome itself. This is the fairest, highest-confidence test of the model's actual predictive accuracy.</p>
{metrics_table("A_STRICT_REAL, ranked by MAE (v4)", strict_rows)}
<div class="callout good-callout"><b>This tier recovered under v4</b> (R&sup2; -1.42 in v3 &rarr; {fnum(metrics(strict_mask,'pred_xgboost')['R2'],2)} with XGBoost, {fnum(m_strict_lgb_v4['R2'],2)} with LightGBM &mdash; both close to or above v1's original 0.487). Excluding the 2 feta rows that broke this tier in v3, the remaining 25 rows score MAE={fnum(m_strict_nonfeta_v4['MAE'],2)}d, R&sup2;={fnum(m_strict_nonfeta_v4['R2'],2)}; the feta pair itself is now MAE={fnum(m_strict_feta_v4['MAE'],1)}d instead of the ~19.5d it was in v3. Full three-way trace in &sect;8.3.</div>
<div class="callout">The Explainable Boosting Machine remains the weakest model on this tier in v4 (R&sup2; = {fnum(m_ebm_strict_v4['R2'],2)}) &mdash; worth knowing if EBM is being used anywhere for its explainability rather than its accuracy.</div>

<h2 id="category">6. Results by cheese category &mdash; every model (v4)</h2>
{''.join(cat_sections)}

<h2 id="control">7. Control (untreated) vs. treatment rows &mdash; every model (v4)</h2>
{''.join(ctl_sections)}

<h2 id="rootcause">8. Root cause analysis</h2>
<h3>8.1 &mdash; Extrapolation was checked and ruled out (again, on v4)</h3>
<p>Same check as in the v1 and v3 reports: if the model were simply being asked to extrapolate past its training range, restricting to in-range rows only should improve results.</p>
{metrics_table("In-range vs. out-of-range inputs (XGBoost, v4)", metrics_row_html("In-range (n="+str(int(in_range_np.sum()))+")", m_in) + metrics_row_html("Out-of-range (n="+str(int((~in_range_np).sum()))+")", m_out))}
<div class="callout"><b>Same result as before:</b> in-range performs worse, not better (R&sup2; {fnum(m_in['R2'],2)} in-range vs {fnum(m_out['R2'],2)} out-of-range). Extrapolation is still not the explanation for v4's weak spots &mdash; both the A_STRICT_REAL fix and the new semi-hard regression are in-distribution calibration effects.</div>

<h3>8.2 &mdash; Hard cheese: the v1&rarr;v3&rarr;v4 label and prediction arc</h3>
<div class="callout proof">
  <b>Parmigiano Reggiano.</b> Real case: {fnum(parm['matrix_ripening_days'],0)} days already aged, paper reports <b>{fnum(parm['shelf_life_days'],0)} days</b>.
  Matching synthetic training rows (hard category, ripening within &plusmn;30% of the real case, controls only) &mdash; median labeled shelf life:
  v1 <b>{fnum(similar_parm_v1['shelf_life_days'].median(),1)}d</b> (n={len(similar_parm_v1)}, inflation {fnum(parm_ratio_v1,2)}&times;) &rarr;
  v3 <b>{fnum(similar_parm_v3['shelf_life_days'].median(),1)}d</b> (n={len(similar_parm_v3)}, inflation {fnum(parm_ratio_v3,2)}&times;) &rarr;
  v4 <b>{fnum(similar_parm_v4['shelf_life_days'].median(),1)}d</b> (n={len(similar_parm_v4)}, inflation {fnum(parm_ratio_v4,2)}&times;).
  The label has kept moving toward the real value across all three versions.
</div>
<div class="callout">
  <b>The model's live output has partly caught up.</b> Mean XGBoost prediction across the Parmigiano test rows: v3 <b>{fnum(parm_actual_v3_mean,1)}d</b> &rarr; v4 <b>{fnum(parm_actual_v4_mean,1)}d</b> &mdash; still well above the real value ({fnum(parm['shelf_life_days'],0)}d), but the gap between label and live output that the v3 report flagged has narrowed, consistent with hard cheese's continued (if incomplete) improvement in &sect;2 and &sect;6.
</div>
<p><b>Reading:</b> hard cheese is the one category recalibrated consistently across both v3 and v4, and it shows a consistent, monotonic improvement in both the label and the live prediction. It is the model of what "targeted recalibration done right" looks like &mdash; contrast with &sect;8.4.</p>

<h3>8.3 &mdash; A_STRICT_REAL / feta: broke in v3, fixed in v4</h3>
<p>Row-by-row comparison of the 2 feta rows across all three versions:</p>
<table class="metrics">
<thead><tr><th>Row ID</th><th>True (d)</th><th>v1 pred</th><th>v1 err</th><th>v3 pred</th><th>v3 err</th><th>v4 pred</th><th>v4 err</th></tr></thead>
<tbody>{feta_rows_html}</tbody>
</table>
<div class="callout good-callout">v1 predicted both rows within about a day; v3 badly overpredicted both (this is what broke the tier's R&sup2;); v4 is back to within a few days of the true value on both rows. Since this report still does not know <i>why</i> the v3 training data mislabeled feta specifically, it also cannot yet confirm whether v4's fix was a deliberate, targeted correction to that same root cause, or an incidental side effect of a broader adjustment to the soft-cheese portion of the label set. Either way, the outcome on these two specific rows is unambiguously better.</div>

<h3>8.4 &mdash; NEW in v4: semi-hard cheese label inflation (processed cheese, kashar, gouda)</h3>
<p>Unlike hard cheese, semi-hard cheese was not a target of the v3 recalibration and scored well in v3 (R&sup2;={fnum(m_semihard_v3['R2'],2)}). In v4 it collapsed (R&sup2;={fnum(m_semihard_v4['R2'],2)}, bias +{fnum(m_semihard_v4['bias'],1)}d). Direct comparison of the v3 vs. v4 training labels for the three semi-hard food matrices that dominate this test set's semi-hard rows:</p>
<table class="metrics">
<thead><tr><th>Food matrix</th><th>n (v3)</th><th>Median label (v3)</th><th>n (v4)</th><th>Median label (v4)</th><th>Change</th></tr></thead>
<tbody>{semihard_label_html}</tbody>
</table>
<div class="callout bad-callout"><b>Proven, not inferred:</b> all three matrices' v4 training labels are substantially higher than their v3 labels &mdash; the opposite direction from what v3 did for hard cheese. This directly explains both the semi-hard collapse and most of the C_SAFETY_EVENT_REAL collapse, since the majority of C_SAFETY_EVENT_REAL rows in this test set are processed-cheese pathogen-challenge cases. Row-level confirmation for the processed-cheese C_SAFETY_EVENT_REAL rows:</div>
<table class="metrics">
<thead><tr><th>Row ID</th><th>True (d)</th><th>Storage</th><th>Indicator</th><th>v3 pred</th><th>v4 pred</th></tr></thead>
<tbody>{pc_rows_html}</tbody>
</table>
<p>The model is genuinely temperature-sensitive here (predictions drop as storage temperature rises across both versions) but is not sensitive to <code>indicator_type</code>/challenge context at all &mdash; a real background-safety control row (true 270d) and a deliberate pathogen-challenge row at the same temperature (true 3&ndash;14d) get nearly identical predictions in both v3 and v4. v4's inflated processed-cheese label made this pre-existing blind spot substantially worse in absolute terms, but did not create it &mdash; it was already present in v3 (see the v3-pred column above), just less severely.</p>

<h2 id="lowerbound">9. Lower-bound compliance, v1 / v3 / v4</h2>
<p>For tiers where the reported value is a floor (paper states "no spoilage observed by day X" &mdash; the true shelf life is at least X), a correct model should predict at or above that floor.</p>
<div class="callout"><b>{fnum(lb_pct,0)}%</b> of {int(lb_mask.sum())} lower-bound-semantics predictions (XGBoost, v4) meet or exceed the reported floor (v1: {fnum(lb_pct_v1,0)}%, v3: {fnum(lb_pct_v3,0)}%). <b>{lb_under_n} rows under-predict</b> a duration the literature has already demonstrated is safely exceeded. Materially unchanged across all three versions &mdash; neither recalibration targeted bound semantics specifically.</div>

<h2 id="papers">10. Per-paper breakdown &mdash; all 34 papers (XGBoost, v4), ranked by MAE (worst first)</h2>
<table>
<thead><tr><th>Paper (DOI / link)</th><th>n</th><th>MAE</th><th>R&sup2;</th><th>Bias</th></tr></thead>
<tbody>{paper_table_rows}</tbody>
</table>
<p class="note">R&sup2; is undefined (&mdash;) for papers contributing a single true-value cluster with near-zero variance &mdash; a data artifact of R&sup2;'s definition, not a model failure indicator for those rows. By worst MAE alone, {worst_paper_doi} (n={worst_paper_m['n']}) ranks first, but at only {fnum(worst_paper_pct_of_total,0)}% of the test set it barely moves pooled statistics. The paper that actually drags down pooled numbers the most is the one combining a large sample with poor accuracy: <b>{dominant_doi}</b> (n={dominant_m['n']}, ~{fnum(dominant_pct_of_total,0)}% of the whole test set, MAE={fnum(dominant_m['MAE'],1)}d, R&sup2;={fnum(dominant_m['R2'],2)}).</p>

<h2 id="worst">11. Worst 30 individual predictions (XGBoost, v4, by absolute error)</h2>
<table>
<thead><tr><th>Row</th><th>Food matrix</th><th>Category</th><th>Tier</th><th>True (d)</th><th>Pred (d)</th><th>Error (d)</th></tr></thead>
<tbody>{worst_rows}</tbody>
</table>

<h2 id="issues">12. Issues identified (v4 state)</h2>
<ol class="issues">
  <li><b>Semi-hard cheese collapsed, root-caused to label inflation.</b> R&sup2; {fnum(m_semihard_v3['R2'],2)} (v3) &rarr; {fnum(m_semihard_v4['R2'],2)} (v4), bias +{fnum(m_semihard_v3['bias'],1)}d &rarr; +{fnum(m_semihard_v4['bias'],1)}d (n=114). Processed cheese/kashar/gouda training labels rose substantially from v3 to v4 (&sect;8.4) &mdash; the opposite direction of the intended recalibration.</li>
  <li><b>C_SAFETY_EVENT_REAL got substantially worse</b> (R&sup2; {fnum(m_safety_v3['R2'],2)} &rarr; {fnum(m_safety_v4['R2'],2)}, n=52), same root cause as above, compounding a pre-existing blind spot: the model is not sensitive to pathogen-challenge context (<code>indicator_type</code>) at all, in v3 or v4.</li>
  <li><b>A_STRICT_REAL is fixed.</b> R&sup2; -1.42 (v3) &rarr; {fnum(metrics(strict_mask,'pred_xgboost')['R2'],2)} (v4, XGBoost) / {fnum(m_strict_lgb_v4['R2'],2)} (v4, LightGBM). The specific feta overprediction that broke this tier in v3 no longer reproduces. Root cause of why feta moved in v3 is still not identified, only that v4 no longer exhibits the symptom.</li>
  <li><b>Hard cheese kept improving, still imperfect.</b> R&sup2; {fnum(m_hard_v3['R2'],2)} (v3) &rarr; {fnum(m_hard_v4['R2'],2)} (v4), and the Parmigiano label-vs-live-output gap flagged in the v3 report narrowed ({fnum(parm_actual_v3_mean,0)}d &rarr; {fnum(parm_actual_v4_mean,0)}d live output, vs a {fnum(similar_parm_v4['shelf_life_days'].median(),0)}d v4 label and a {fnum(parm['shelf_life_days'],0)}d real value) but has not closed.</li>
  <li><b>Pooled/overall statistics fell back toward v1-era levels</b> (R&sup2; 0.445 v3 &rarr; {fnum(metrics(mask_all_v4,'pred_xgboost')['R2'],3)} v4) &mdash; driven almost entirely by the semi-hard/safety-event regression above, not a broad-based decline.</li>
  <li><b>Lower-bound semantics still fail on roughly half of applicable rows</b> ({lb_under_n} of {int(lb_mask.sum())}, {fnum(100-lb_pct,0)}%), unchanged across all three model generations.</li>
  <li><b>EBM remains the weakest model on the highest-confidence tier</b> (A_STRICT_REAL R&sup2; = {fnum(m_ebm_strict_v4['R2'],2)}), consistent across v1/v3/v4.</li>
  <li><b>Pooled/overall statistics remain paper-dominated, not sample-representative.</b> One paper ({dominant_doi}, n={dominant_m['n']}, ~{fnum(dominant_pct_of_total,0)}% of the test set, MAE={fnum(dominant_m['MAE'],1)}d) single-handedly drags every pooled number; per-tier and per-category breakdowns remain more trustworthy than the single pooled R&sup2;.</li>
</ol>

<h2 id="recommendations">13. Recommendations</h2>
<p><b>What v4 already achieved, and shouldn't be undone:</b> the A_STRICT_REAL/feta fix and hard cheese's continued improvement are both real and should be preserved. The problem is not that v4 recalibrated &mdash; it's that the recalibration of semi-hard matrices (processed cheese, kashar, gouda) moved the label in the wrong direction while other matrices moved correctly.</p>
<p><b>Recommended, in order of expected payoff:</b></p>
<ol>
  <li>Re-examine the specific v4 label-generation step for processed cheese, kashar, and gouda &mdash; these three matrices' labels moved substantially <i>up</i> from v3 (&sect;8.4), while the overall recalibration intent (based on the v3&rarr;v4 fixes seen elsewhere) appears to have been to bring hard/A_STRICT_REAL matrices <i>down</i> toward real values. This looks like a sign-flipped or mis-scoped adjustment for this specific subset, not a fundamental data problem.</li>
  <li>Separately, address the pathogen-challenge blind spot directly: add <code>indicator_type</code>-aware short-shelf-life training examples for processed cheese (and any other matrix with C_SAFETY_EVENT_REAL coverage) so the model can learn that a deliberate high-inoculum challenge study produces a very different outcome than a background-safety control at the same temperature. This is a data-coverage gap, not a calibration-scale problem, and predates v4.</li>
  <li>Continue the Parmigiano-style approach for hard cheese: the label-to-live-output gap is narrowing but not closed; keep tracking it explicitly in the next iteration rather than assuming the label fix alone will finish the job.</li>
  <li>Soft cheese continues to need no intervention (R&sup2; = {fnum(m_soft_v4['R2'],2)}).</li>
  <li>Given the whack-a-mole pattern across v3&rarr;v4 (fixing hard/A_STRICT_REAL while breaking semi-hard), any future recalibration pass should re-run this full 319-case evaluation <i>before</i> declaring success, specifically checking every category and tier this report tracks, not just the one that motivated the change.</li>
</ol>

<h2 id="appendix" class="page-break">14. Appendix &mdash; full per-row results, all 319 rows, all 4 models (v4)</h2>
<p class="small">Sorted by cheese category, then confidence tier, then food matrix. "Err" = prediction &minus; true value in days (positive = overprediction, negative = underprediction).</p>
<table style="font-size:8px;">
<thead><tr>
  <th>Row ID</th><th>Food matrix</th><th>Category</th><th>Tier</th><th>True (d)</th>
  <th>RF</th><th>Err</th><th>LightGBM</th><th>Err</th><th>XGBoost</th><th>Err</th><th>EBM</th><th>Err</th>
</tr></thead>
<tbody>{full_table_rows}</tbody>
</table>

<p class="small" style="margin-top:20px;">Report generated from stress_test_319_predictions.csv, produced by evaluate_319_stress_test.py against the live v4 production models (artifacts/, retrained from scratch on CHEESE_SHELF_LIFE_TARGETED_V4_READY_TO_TRAIN.xlsx). v1 and v3 comparison figures are read from {V1_BACKUP_DIR}/stress_test_319_predictions.csv and {V3_BACKUP_DIR}/stress_test_319_predictions.csv respectively, both backups taken immediately before their successor retrain. No retraining occurred in the course of generating this evaluation or report.</p>

</body></html>
"""

with open("results_report.html", "w", encoding="utf-8") as f:
    f.write(HTML)

print(f"Report generated: results_report.html ({len(df)} rows in appendix)")
