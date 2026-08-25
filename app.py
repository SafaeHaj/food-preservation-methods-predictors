#!/usr/bin/env python
"""
Shelf-Life Regression Dashboard — reads ONLY local artifacts produced by
`python train_models.py` (artifacts/*.json, predictions.parquet,
artifacts/models/*). No MLflow, no server, no retraining.

Usage:
    python app.py
Then open http://127.0.0.1:8050
"""
from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, callback, ctx, dcc, html

from model_service import BEST_MODEL_KEY, MODEL_LABELS, NONE_INGREDIENT_DESCRIPTORS, ModelService

SERVICE = ModelService()
CORE_MODELS = [m for m in ("random_forest", "lightgbm", "xgboost", "ebm", "lstm") if m in SERVICE.models]

MODEL_BLURBS = {
    "random_forest": "Bagged ensemble of decision trees; robust baseline, resistant to overfitting.",
    "lightgbm": "Gradient-boosted trees optimized for speed on tabular data.",
    "xgboost": "Gradient-boosted trees with regularization; strong general-purpose accuracy.",
    "ebm": "Generalized additive model with pairwise interactions; every prediction fully decomposable.",
    "lstm": "Recurrent network run on the feature vector as an artificial sequence — an experimental benchmark, not a natural fit for this cross-sectional data.",
}

# ── Palette ──────────────────────────────────────────────────────────────────

FA_CDN = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css"
GOOGLE_FONTS = (
    "https://fonts.googleapis.com/css2?"
    "family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&"
    "family=Inter:wght@400;500;600;700;800&"
    "family=JetBrains+Mono:wght@400;500;600;700&display=swap"
)

NAVY, MAROON, MAROON_DARK, BLUE_ACCENT = "#1A1A2E", "#8C1D30", "#6E1424", "#3E6FA8"
GOOD, WARNING, CRITICAL, TEXT_MUTED, TEXT_PRIMARY = "#1E8A5F", "#B4791F", "#B4322B", "#6B6B76", "#201F2B"
BORDER, SURFACE2, SURFACE3 = "#E6E2E0", "#F7F4F2", "#FAF8F7"
MODEL_COLOR = {"random_forest": "#1E8A5F", "lightgbm": "#8C1D30", "xgboost": "#3E6FA8", "ebm": "#B4791F", "lstm": "#6B6B76"}

app = Dash(__name__, title="Shelf-Life Studio", external_stylesheets=[FA_CDN, GOOGLE_FONTS],
           suppress_callback_exceptions=True)
server = app.server


# ── UI atoms ─────────────────────────────────────────────────────────────────

def _icon(cls: str) -> html.I:
    return html.I(className=f"fa-solid {cls}")


def _badge(text: str, kind: str = "muted") -> html.Span:
    return html.Span(text, className=f"badge badge--{kind}")


def _kpi(label: str, value: str, icon: str = "fa-circle", color: str = MAROON, sub: str | None = None,
         selected: bool = False) -> html.Div:
    return html.Div([
        html.Div([_icon(icon)], className="kpi-icon-circle"),
        html.Div([
            html.Span(label, className="kpi-label"),
            html.Span("Selected", className="kpi-selected-pill") if selected else None,
        ], className="kpi-top"),
        html.Div(value, className="kpi-value"),
        html.Div(sub, className="kpi-sub") if sub else None,
    ], className="kpi-tile" + (" kpi-tile--accent" if selected else ""), style={"--kpi-color": color})


def _kpi_grid(*tiles) -> html.Div:
    return html.Div(list(tiles), className="kpi-grid")


def _card(children, title: str | None = None, caption: str | None = None, icon: str | None = None) -> html.Div:
    header = []
    if title or caption:
        title_children = [_icon(icon), html.Span(title or "", className="card-title")] if icon else [html.Span(title or "", className="card-title")]
        header.append(html.Div([html.Div(title_children, className="card-title-row-v2"),
                                html.Span(caption or "", className="card-caption")], className="card-title-row"))
    return html.Div(header + [children] if header else [children], className="card")


def _empty_state(icon: str, title: str, message: str) -> html.Div:
    return html.Div([
        html.Div(_icon(icon), className="empty-icon"),
        html.Div(title, className="empty-title"),
        html.Div(message, className="empty-msg"),
    ], className="empty-state")


def _table(header: list[str], rows: list[list], highlight_index: int | None = None) -> html.Div:
    body_rows = []
    for idx, r in enumerate(rows):
        row_cls = "row-highlight" if idx == highlight_index else None
        body_rows.append(html.Tr([html.Td(c) for c in r], className=row_cls))
    return html.Div(html.Table([
        html.Thead(html.Tr([html.Th(h) for h in header])),
        html.Tbody(body_rows),
    ], className="data-table"), className="table-scroll")


def _labeled_field(label: str, control, required: bool = False, badge: str | None = None,
                    error_id: str | None = None, source_id: str | None = None) -> html.Div:
    label_row = [html.Span(label, className="field-label")]
    if required:
        label_row.append(html.Span(" *", className="field-required-mark"))
    if badge:
        label_row.append(_badge(badge, "muted"))
    if source_id:
        label_row.append(html.Span("Dataset default", id=source_id, className="badge badge--source"))
    children = [html.Div(label_row, className="field-label-row"), control]
    if error_id:
        children.append(html.Div(id=error_id, className="field-error"))
    return html.Div(children, className="field")


def _collapsible(summary: str, children) -> html.Details:
    return html.Details([html.Summary(summary, className="panel-summary"),
                         html.Div(children, className="panel-body")], className="panel-collapse")


def _style_fig(fig: go.Figure, height: int = 320, title: str | None = None, showlegend: bool = True) -> go.Figure:
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0.012)",
        font=dict(color=TEXT_MUTED, family="Inter, sans-serif", size=12),
        title=dict(text=title, font=dict(color=TEXT_PRIMARY, size=13.5), x=0.01) if title else None,
        height=height, showlegend=showlegend, margin=dict(l=8, r=8, t=44 if title else 16, b=48),
        legend=dict(orientation="h", y=-0.18, x=0),
        colorway=[MAROON, BLUE_ACCENT, GOOD, WARNING, TEXT_MUTED],
    )
    fig.update_xaxes(gridcolor="rgba(0,0,0,0.07)", linecolor=BORDER)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0.07)", linecolor=BORDER)
    return fig


def _graph(fig: go.Figure, graph_id: str | None = None) -> dcc.Graph:
    kwargs = {"id": graph_id} if graph_id else {}
    return dcc.Graph(figure=fig, config={"displayModeBar": False}, **kwargs)


def _page_header(title: str, subtitle: str) -> html.Div:
    return html.Div([
        html.H1(title, className="page-header-title-v2"),
        html.P(subtitle, className="page-header-sub-v2"),
    ], className="page-header-v2")


def _footer() -> html.Div:
    trained_at = SERVICE.manifest.get("created_at_utc", "")
    trained_label = trained_at.split("T")[0] if trained_at else "unknown"
    return html.Div([
        html.Span(f"Dataset: {SERVICE.manifest['dataset_path']}"),
        html.Span("•", className="footer-dot"),
        html.Span(f"Models trained: {trained_label}"),
        html.Span("•", className="footer-dot"),
        html.Span("Shelf-Life Studio"),
    ], className="page-footer")


def model_metric(model: str, key: str) -> float:
    return SERVICE.metrics.get(model, {}).get(key, float("nan"))


# ── Navigation ───────────────────────────────────────────────────────────────

NAV_ITEMS = [
    ("/", "Home", "fa-house"),
    ("/datasets", "Datasets", "fa-database"),
    ("/modeling", "Modeling", "fa-diagram-project"),
    ("/prediction", "Prediction", "fa-flask"),
    ("/results", "Results", "fa-ranking-star"),
    ("/explainability", "Explainability", "fa-lightbulb"),
    ("/how-it-works", "How it works", "fa-circle-info"),
    ("/references", "References", "fa-book"),
]
PAGE_TITLES = {path: label for path, label, _ in NAV_ITEMS}


def _sidebar() -> html.Div:
    return html.Div([
        html.Div([
            html.Div(_icon("fa-shield-halved"), className="brand-mark"),
            html.Div([
                html.Span("Shelf-Life Studio", className="brand-title"),
                html.Span("Food Science ML", className="brand-sub"),
            ], className="brand-text"),
        ], className="brand"),
        html.Div([
            dcc.Link([_icon(icon), html.Span(label)], href=path, id=f"navlink{path}", className="nav-item")
            for path, label, icon in NAV_ITEMS
        ], className="nav-list", id="nav-list"),
        html.Div([
            html.Div([_icon("fa-code-branch"), html.Span("v1.0.0")], className="sidebar-meta-row"),
            html.Div([_icon("fa-server"), html.Span("Local artifacts, no live retraining")], className="sidebar-meta-row"),
        ], className="sidebar-footer"),
    ], className="sidebar")


def _topbar() -> html.Div:
    return html.Div([
        html.Div(id="breadcrumb", className="breadcrumb"),
        html.Div([
            dcc.Input(id="global-search", type="text", placeholder="Search pages, models, features…",
                      className="search-input", debounce=True),
            _icon("fa-magnifying-glass"),
        ], className="search-box"),
        html.Div([
            html.Div(_icon("fa-circle-user"), className="profile-icon"),
        ], className="topbar-actions"),
    ], className="topbar")


# ── App shell ────────────────────────────────────────────────────────────────

app.layout = html.Div([
    dcc.Location(id="url", refresh=False),
    dcc.Store(id="last-prediction-store"),
    _sidebar(),
    html.Div([
        _topbar(),
        html.Div(id="page-content", className="page-content"),
    ], className="main-col"),
], className="app-shell")


@callback(
    [Output(f"navlink{path}", "className") for path, _, _ in NAV_ITEMS],
    Output("breadcrumb", "children"),
    Input("url", "pathname"),
)
def _update_nav(pathname: str):
    pathname = pathname or "/"
    classes = ["nav-item active" if path == pathname else "nav-item" for path, _, _ in NAV_ITEMS]
    label = PAGE_TITLES.get(pathname, "Home")
    crumb = html.Span([html.Span("Home"), _icon("fa-chevron-right") if pathname != "/" else None,
                       html.Span(label) if pathname != "/" else None])
    return classes + [crumb]


@callback(Output("url", "pathname"), Input("global-search", "value"), prevent_initial_call=True)
def _search_jump(query: str):
    if not query:
        return dash_no_update()
    q = query.strip().lower()
    for path, label, _ in NAV_ITEMS:
        if q in label.lower():
            return path
    for m in CORE_MODELS:
        if q in MODEL_LABELS[m].lower() or q in m.lower():
            return "/modeling"
    return dash_no_update()


def dash_no_update():
    import dash
    return dash.no_update


# ── Page: Home ───────────────────────────────────────────────────────────────

def page_home() -> html.Div:
    df = SERVICE.full_df
    n_total = len(df)
    n_real = int((df["data_origin"] == "real_paper_derived").sum())
    n_contexts = df["context_id"].nunique()
    n_controls = int((df["is_control"] == 1).sum())
    n_treatments = n_total - n_controls

    kpis = _kpi_grid(
        _kpi("Total rows", f"{n_total:,}", "fa-database", MAROON, sub="training_data sheet"),
        _kpi("Contexts", f"{n_contexts:,}", "fa-globe", BLUE_ACCENT, sub="Environmental / processing settings"),
        _kpi("Target variable", "shelf_life_days", "fa-hourglass-half", TEXT_MUTED, sub=f"{df['shelf_life_days'].min():.2f}–{df['shelf_life_days'].max():.2f} days"),
    )

    pipeline_steps = [
        ("fa-database", "Data curation", "Load training_data, drop identifiers & provenance flags"),
        ("fa-clipboard-check", "Schema validation", "Auto-detect numeric / categorical / binary columns"),
        ("fa-table-cells", "Feature preparation", "Impute, encode, scale per model family"),
        ("fa-brain", "Model training", "Fit 5 independent models, early-stop where supported"),
        ("fa-chart-line", "Prediction", "Compare a control formulation against candidates"),
        ("fa-lightbulb", "Explainability", "Permutation importance + EBM shapes + local factors"),
    ]
    pipeline = html.Div([
        html.Div([
            html.Div(_icon(icon), className="pipeline-icon"),
            html.Div(f"{i}", className="pipeline-num"),
            html.Div(title, className="pipeline-title"),
            html.Div(desc, className="pipeline-desc"),
        ], className="pipeline-step")
        for i, (icon, title, desc) in enumerate(pipeline_steps, start=1)
    ], className="pipeline-row")

    hist = px.histogram(df, x="shelf_life_days", nbins=30, color_discrete_sequence=[MAROON])
    _style_fig(hist, height=280, showlegend=False)
    hist.update_xaxes(title="Shelf life (days)")

    fam = df[df["primary_ingredient_family"] != "none"]["primary_ingredient_family"].value_counts()
    fam_fig = go.Figure(go.Bar(x=fam.values, y=fam.index, orientation="h", marker_color=MAROON))
    _style_fig(fam_fig, height=280, showlegend=False)
    fam_fig.update_xaxes(title="Rows")

    scatter = px.scatter(df.sample(min(1000, len(df)), random_state=42), x="storage_temperature_c", y="shelf_life_days",
                         color_discrete_sequence=[BLUE_ACCENT])
    _style_fig(scatter, height=280, showlegend=False)
    scatter.update_xaxes(title="Storage temperature (°C)")
    scatter.update_yaxes(title="Shelf life (days)")
    try:
        corr = float(df["storage_temperature_c"].corr(df["shelf_life_days"]))
    except Exception:
        corr = float("nan")

    schema_rows = []
    for c in SERVICE.feature_cols[:8]:
        schema_rows.append([c, str(df[c].dtype), str(df[c].dropna().iloc[0]) if df[c].notna().any() else "—"])

    return html.Div([
        _page_header("Shelf-Life Prediction Workspace", "A machine-learning platform for predicting cheese shelf life from formulation, processing, and storage attributes."),
        kpis,
        _card(pipeline, title="Shared modeling pipeline", caption="Every page below reads the same trained artifacts.", icon="fa-route"),
        html.Div([
            _card(_graph(hist), title="Shelf-life distribution (days)", icon="fa-chart-column"),
            _card(_graph(fam_fig), title="Rows by ingredient family", icon="fa-flask-vial"),
            _card(_graph(scatter), title="Storage temperature vs. shelf life", caption=f"Pearson r = {corr:.2f}", icon="fa-temperature-half"),
        ], className="row-flex row-flex-3"),
        _card(_table(["Column", "Type", "Example"], schema_rows), title="Schema preview", caption="First 8 of 34 features — full list on Datasets", icon="fa-table-list"),
        _footer(),
    ])


# ── Page: Datasets ───────────────────────────────────────────────────────────

def page_datasets() -> html.Div:
    df = SERVICE.full_df
    n_total = len(df)
    n_real = int((df["data_origin"] == "real_paper_derived").sum())

    origin_rows = [[k, f"{v:,}", f"{v / n_total * 100:.1f}%"] for k, v in df["data_origin"].value_counts().items()]
    origin_table = _card(_table(["Origin", "Rows", "Share"], origin_rows), title="Data origin breakdown", icon="fa-code-branch")

    matrix_counts = df["food_matrix"].value_counts()
    matrix_fig = go.Figure(go.Bar(x=matrix_counts.index, y=matrix_counts.values, marker_color=MAROON))
    _style_fig(matrix_fig, height=280, showlegend=False)

    indicator_counts = df["indicator_type"].value_counts()
    ind_fig = go.Figure(go.Pie(labels=indicator_counts.index, values=indicator_counts.values,
                               marker_colors=[MAROON, BLUE_ACCENT, GOOD, WARNING], hole=0.55))
    _style_fig(ind_fig, height=280, showlegend=True)

    missing = df[SERVICE.feature_cols].isna().mean().sort_values(ascending=False)
    missing = missing[missing > 0]
    if len(missing):
        miss_rows = [[c, f"{v * 100:.1f}%"] for c, v in missing.items()]
        miss_card = _card(_table(["Column", "Missing"], miss_rows), title="Missing values", caption="Median-imputed at training time", icon="fa-triangle-exclamation")
    else:
        miss_card = _card(_empty_state("fa-circle-check", "No missing values", "Every feature column is fully populated."), title="Missing values", icon="fa-triangle-exclamation")

    schema_rows = []
    for c in SERVICE.feature_cols:
        kind = "numeric" if c in SERVICE.numeric_cols else ("binary" if c in SERVICE.binary_cols else "categorical")
        miss_pct = df[c].isna().mean() * 100
        example = df[c].dropna().iloc[0] if df[c].notna().any() else "—"
        schema_rows.append([c, kind, str(df[c].dtype), f"{miss_pct:.1f}%", str(example)])
    schema_table = _card(_table(["Column", "Role", "Type", "Missing", "Example"], schema_rows),
                         title="Full feature schema", caption=f"{len(SERVICE.feature_cols)} features · target: {SERVICE.schema['target']}", icon="fa-table-list")

    return html.Div([
        _page_header("Datasets", "Composition, provenance, and schema of the training workbook."),
        _kpi_grid(
            _kpi("Total rows", f"{n_total:,}", "fa-database", MAROON),
            _kpi("Food matrices", str(df["food_matrix"].nunique()), "fa-cheese", BLUE_ACCENT),
            _kpi("Contexts", f"{df['context_id'].nunique():,}", "fa-globe", WARNING, sub="~5 rows per context"),
        ),
        html.Div([origin_table,
                 _card(_graph(matrix_fig), title="Rows by food matrix", icon="fa-cheese"),
                 _card(_graph(ind_fig), title="Rows by indicator type", icon="fa-vial")], className="row-flex row-flex-3"),
        miss_card,
        schema_table,
        _footer(),
    ])


# ── Page: Modeling ───────────────────────────────────────────────────────────

def page_modeling() -> html.Div:
    best = SERVICE.best_model
    ranked = sorted(CORE_MODELS, key=lambda m: model_metric(m, "validation_rmse"))
    rows = []
    for m in ranked:
        name_cell = html.Span([_icon("fa-star") if m == best else None, MODEL_LABELS[m]], className="model-name-cell")
        rows.append([
            name_cell,
            f"{model_metric(m, 'validation_r2'):.3f}", f"{model_metric(m, 'test_r2'):.3f}",
            f"{model_metric(m, 'validation_rmse'):.2f}", f"{model_metric(m, 'test_rmse'):.2f}",
            f"{model_metric(m, 'validation_mae'):.2f}", f"{model_metric(m, 'test_mae'):.2f}",
            f"{model_metric(m, 'training_duration_sec'):.1f} s",
        ])
    table = _card(_table(
        ["Model", "Validation R² ↑", "Test R² ↑", "Validation RMSE ↓", "Test RMSE ↓", "Validation MAE ↓", "Test MAE ↓", "Training time"],
        rows, highlight_index=0,
    ), title="Model comparison", caption="* Lower is better for RMSE / MAE", icon="fa-ranking-star")

    kpis = _kpi_grid(
        _kpi("Best model", MODEL_LABELS[best], "fa-trophy", GOOD, sub="Lowest validation RMSE", selected=True),
        _kpi("Train rows", f"{SERVICE.manifest['n_train']:,}", "fa-book-open", MAROON, sub="70% of contexts"),
        _kpi("Validation rows", f"{SERVICE.manifest['n_validation']:,}", "fa-clipboard-check", BLUE_ACCENT, sub="15% of contexts"),
        _kpi("Test rows", f"{SERVICE.manifest['n_test']:,}", "fa-flask", WARNING, sub="15% of contexts, held out"),
    )

    bar = go.Figure()
    bar.add_trace(go.Bar(name="Validation RMSE", x=[MODEL_LABELS[m] for m in ranked],
                         y=[model_metric(m, "validation_rmse") for m in ranked], marker_color=MAROON,
                         text=[f"{model_metric(m, 'validation_rmse'):.2f}" for m in ranked], textposition="outside"))
    bar.add_trace(go.Bar(name="Test RMSE", x=[MODEL_LABELS[m] for m in ranked],
                         y=[model_metric(m, "test_rmse") for m in ranked], marker_color=BLUE_ACCENT,
                         text=[f"{model_metric(m, 'test_rmse'):.2f}" for m in ranked], textposition="outside"))
    _style_fig(bar, height=360)
    bar.update_layout(barmode="group", legend=dict(orientation="h", y=1.14, x=0))

    run_rows = [
        ["Random seed", str(SERVICE.manifest["random_seed"])],
        ["Dataset", SERVICE.manifest["dataset_path"]],
        ["Total rows (real / synthetic)", f"{SERVICE.manifest['n_total']:,} ({SERVICE.manifest['n_real_paper_derived']} / {SERVICE.manifest['n_synthetic']:,})"],
        ["Train / validation / test rows", f"{SERVICE.manifest['n_train']:,} / {SERVICE.manifest['n_validation']:,} / {SERVICE.manifest['n_test']:,}"],
        ["Models trained", ", ".join(MODEL_LABELS[m] for m in SERVICE.manifest["models_trained"])],
        ["Total training duration", f"{SERVICE.manifest['total_training_duration_sec']:.1f} s"],
        ["Trained at (UTC)", SERVICE.manifest["created_at_utc"].split(".")[0]],
    ]
    run_card = _card(_table(["Field", "Value"], run_rows), title="Training run details", caption="Retraining is CLI-only (python train_models.py) — never triggered from this dashboard", icon="fa-terminal")

    model_cards = html.Div([
        _card(html.Div([
            html.Div(MODEL_LABELS[m], className="model-card-title"),
            html.Div(MODEL_BLURBS[m], className="model-card-desc"),
        ]), title=None)
        for m in CORE_MODELS
    ], className="row-flex row-flex-5")

    return html.Div([
        _page_header("Modeling", "Training and validation results for every model, computed once and read from saved artifacts."),
        kpis, table,
        _card(_graph(bar), title="Validation vs. test RMSE by model", caption="Lower values indicate better performance.", icon="fa-chart-line"),
        run_card,
        model_cards,
        _footer(),
    ])


# ── Explainability chart helpers (shared with Explainability page) ──────────

def _actual_vs_predicted_fig(model: str, split: str = "test") -> go.Figure:
    sub = SERVICE.predictions.query("model == @model and split == @split")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sub["y_true"], y=sub["y_pred"], mode="markers",
                             marker=dict(color=MODEL_COLOR.get(model, MAROON), size=6, opacity=0.55), name="predictions"))
    lims = [0, max(sub["y_true"].max(), sub["y_pred"].max()) * 1.05]
    fig.add_trace(go.Scatter(x=lims, y=lims, mode="lines", line=dict(color=CRITICAL, dash="dash"), name="ideal"))
    _style_fig(fig, height=340, title=f"Actual vs. predicted ({split})", showlegend=False)
    fig.update_xaxes(title="Actual shelf life (days)")
    fig.update_yaxes(title="Predicted shelf life (days)")
    return fig


def _residual_fig(model: str, split: str = "test") -> go.Figure:
    sub = SERVICE.predictions.query("model == @model and split == @split").copy()
    sub["residual"] = sub["y_true"] - sub["y_pred"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sub["y_pred"], y=sub["residual"], mode="markers",
                             marker=dict(color=MODEL_COLOR.get(model, MAROON), size=6, opacity=0.55)))
    fig.add_hline(y=0, line_color=CRITICAL, line_dash="dash")
    _style_fig(fig, height=300, title=f"Residuals vs. predicted ({split})", showlegend=False)
    fig.update_xaxes(title="Predicted shelf life (days)")
    fig.update_yaxes(title="Residual (actual - predicted, days)")
    return fig


def _residual_hist_fig(model: str, split: str = "test") -> go.Figure:
    sub = SERVICE.predictions.query("model == @model and split == @split").copy()
    sub["residual"] = sub["y_true"] - sub["y_pred"]
    fig = px.histogram(sub, x="residual", nbins=30, color_discrete_sequence=[MODEL_COLOR.get(model, MAROON)])
    _style_fig(fig, height=280, title="Residual distribution", showlegend=False)
    fig.update_xaxes(title="Residual (days)")
    return fig


def _curve_fig(model: str) -> html.Div:
    curve = SERVICE.curves.get(model)
    if not curve:
        return _empty_state("fa-chart-line", "No training curve available", "This model does not have a stored curve.")
    fig = go.Figure()
    if curve["type"] == "loss_curve":
        fig.add_trace(go.Scatter(y=curve["train_loss"], mode="lines", name="train loss", line=dict(color=MAROON, width=2)))
        fig.add_trace(go.Scatter(y=curve["val_loss"], mode="lines", name="validation loss", line=dict(color=BLUE_ACCENT, width=2)))
        _style_fig(fig, height=300, title="Training / validation loss (RMSE)")
        fig.update_xaxes(title="Boosting round / epoch")
    else:
        fig.add_trace(go.Scatter(x=curve["train_sizes"], y=curve["train_r2"], mode="lines+markers", name="train R²", line=dict(color=MAROON, width=2)))
        fig.add_trace(go.Scatter(x=curve["train_sizes"], y=curve["val_r2"], mode="lines+markers", name="validation R²", line=dict(color=BLUE_ACCENT, width=2)))
        _style_fig(fig, height=300, title="Learning curve (R² vs. training-set size)")
        fig.update_xaxes(title="Training rows used")
    return _graph(fig)


def _importance_fig(model: str, kind: str) -> html.Div:
    imp = SERVICE.feature_importance.get(model, {}).get(kind)
    if not imp:
        return _empty_state("fa-chart-bar", f"No {kind} importance available", "This model does not support this importance type.")
    top = sorted(imp.items(), key=lambda kv: abs(kv[1]), reverse=True)[:20][::-1]
    fig = go.Figure(go.Bar(x=[v for _, v in top], y=[k for k, _ in top], orientation="h",
                           marker_color=MODEL_COLOR.get(model, MAROON)))
    _style_fig(fig, height=max(320, 22 * len(top)), title=f"Top {len(top)} features ({kind})", showlegend=False)
    return _graph(fig)


def _category_error_card(model: str) -> html.Div:
    cat_err = SERVICE.category_errors.get(model, {})
    if not cat_err:
        return _empty_state("fa-table", "No category breakdown available", "")
    sections = []
    for col, groups in cat_err.items():
        rows = sorted(groups.items(), key=lambda kv: kv[1]["mae"], reverse=True)[:8]
        sections.append(_card(_table(["Category", "Test MAE (days)", "n"],
                                     [[k, f"{v['mae']:.2f}", v["n"]] for k, v in rows]), title=col))
    return html.Div(sections, className="row-flex")


def _ebm_shape_section(model: str) -> html.Div:
    if model != "ebm":
        return _empty_state("fa-chart-area", "Shape functions are EBM-only",
                            "Select the Explainable Boosting Machine to see global shape functions.")
    imp = SERVICE.feature_importance["ebm"]["native"]
    top_terms = sorted(imp.items(), key=lambda kv: abs(kv[1]), reverse=True)[:4]
    figs = []
    for term, _ in top_terms:
        curve = None
        try:
            ebm_model = SERVICE.models["ebm"]
            names = list(ebm_model.explain_global().data()["names"])
            if term in names:
                idx = names.index(term)
                d = ebm_model.explain_global().data(idx)
                curve = d
        except Exception:
            curve = None
        if curve is None:
            continue
        fig = go.Figure()
        if curve["type"] == "univariate" and len(curve["names"]) == len(curve["scores"]) + 1:
            fig.add_trace(go.Scatter(x=curve["names"][:-1], y=curve["scores"], mode="lines", line=dict(color=WARNING, width=2), line_shape="hv"))
        else:
            fig.add_trace(go.Bar(x=[str(n) for n in curve["names"]], y=curve["scores"], marker_color=WARNING))
        _style_fig(fig, height=280, title=f"Shape function: {term}", showlegend=False)
        figs.append(_card(_graph(fig)))
    return html.Div(figs, className="row-flex") if figs else _empty_state("fa-chart-area", "No shape data", "")


def render_model_details(model: str) -> html.Div:
    m = SERVICE.metrics[model]
    overfit_gap = m["overfitting_gap_r2"]
    kpis = _kpi_grid(
        _kpi("Validation R²", f"{m['validation_r2']:.3f}", "fa-bullseye", MAROON),
        _kpi("Test R²", f"{m['test_r2']:.3f}", "fa-bullseye", BLUE_ACCENT),
        _kpi("Test RMSE", f"{m['test_rmse']:.2f} d", "fa-ruler", WARNING),
        _kpi("Test MAPE", f"{m['test_mape_pct']:.1f}%" if not np.isnan(m["test_mape_pct"]) else "n/a", "fa-percent", GOOD),
        _kpi("Overfitting gap (train-val R²)", f"{overfit_gap:+.3f}", "fa-scale-balanced",
             GOOD if abs(overfit_gap) < 0.05 else (WARNING if abs(overfit_gap) < 0.15 else CRITICAL)),
        _kpi("Trainable params", f"{m.get('n_trainable_params') or '—':,}" if m.get("n_trainable_params") else "—", "fa-microchip", TEXT_MUTED),
    )
    metrics_table = _card(_table(
        ["Split", "R²", "RMSE", "MAE", "Median AE"],
        [[s.title(), f"{m[f'{s}_r2']:.3f}", f"{m[f'{s}_rmse']:.2f}", f"{m[f'{s}_mae']:.2f}", f"{m[f'{s}_median_ae']:.2f}"]
         for s in ("train", "validation", "test")],
    ), title="Complete metrics", icon="fa-table")

    charts_row1 = html.Div([_card(_graph(_actual_vs_predicted_fig(model))), _card(_graph(_residual_fig(model)))], className="row-flex")
    charts_row2 = html.Div([_card(_graph(_residual_hist_fig(model))), _card(_curve_fig(model), title="Training diagnostic")], className="row-flex")

    importance_row = html.Div([
        _card(_importance_fig(model, "permutation"), title="Permutation importance (cross-model consistent)", icon="fa-arrows-left-right"),
        _card(_importance_fig(model, "native"), title="Native importance", icon="fa-tree") if "native" in SERVICE.feature_importance.get(model, {})
        else _card(_empty_state("fa-chart-bar", "No native importance", "This model family has no native importance measure."), title="Native importance"),
    ], className="row-flex")

    return html.Div([
        kpis, metrics_table, charts_row1, charts_row2, importance_row,
        _card(_ebm_shape_section(model), title="EBM shape functions", icon="fa-chart-area") if model == "ebm" else None,
        _card(_category_error_card(model), title="Test error by category", icon="fa-layer-group"),
    ])


def _last_prediction_local_factors_card(store_data: dict | None) -> html.Div:
    if not store_data:
        return _card(_empty_state("fa-flask", "No prediction yet", "Run a prediction on the Prediction page to see local factors for that specific formulation here."),
                    title="Local explanation of your last prediction", icon="fa-magnifying-glass-chart")
    top_cand = store_data["candidates"][0]
    factors = SERVICE.local_explanation(top_cand["model"], top_cand["row"], top_k=8)
    return _card(html.Ul([html.Li(f"{f['feature']}: {f['contribution']:+.2f} days") for f in factors]),
                title=f"Local explanation — {top_cand['candidate_name']} (your last prediction)",
                caption="Exact for EBM, permutation-based otherwise", icon="fa-magnifying-glass-chart")


def page_explainability_shell() -> html.Div:
    return html.Div([
        _page_header("Explainability", "Understand how each model makes its predictions, globally and for your most recent query."),
        _card(_labeled_field("Select a model", dcc.Dropdown(
            id="details-model-selector",
            options=[{"label": MODEL_LABELS[m], "value": m} for m in CORE_MODELS],
            value=SERVICE.best_model, clearable=False,
        ))),
        html.Div(id="details-content"),
        html.Div(id="last-prediction-explain-content"),
        _footer(),
    ])


@callback(Output("details-content", "children"), Input("details-model-selector", "value"))
def _update_details(model: str) -> html.Div:
    return render_model_details(model)


@callback(Output("last-prediction-explain-content", "children"), Input("last-prediction-store", "data"))
def _update_last_prediction_explain(store_data):
    return _last_prediction_local_factors_card(store_data)


# ── Page: Prediction ─────────────────────────────────────────────────────────

SHARED_REQUIRED_FIELDS = [
    ("food_matrix", "categorical", "Food matrix"),
    ("storage_temperature_c", "numeric", "Storage temperature (°C)"),
    ("packaging_type", "categorical", "Packaging type"),
    ("indicator_type", "categorical", "Indicator type"),
    ("indicator_threshold_log_cfu_g", "numeric", "Indicator threshold (log CFU/g)"),
    ("initial_indicator_log_cfu_g", "numeric", "Initial indicator count (log CFU/g)"),
]
MATRIX_DESCRIPTOR_FIELDS = [
    ("cheese_category", "categorical", "Cheese category"),
    ("fresh_unripened_flag", "binary", "Fresh / unripened"),
    ("matrix_ph", "numeric", "pH"),
    ("matrix_water_activity", "numeric", "Water activity"),
    ("matrix_moisture_pct", "numeric", "Moisture (%)"),
    ("matrix_fat_pct", "numeric", "Fat (%)"),
    ("matrix_protein_pct", "numeric", "Protein (%)"),
    ("matrix_salt_pct", "numeric", "Salt (%)"),
    ("matrix_ripening_days", "numeric", "Ripening days"),
]
PROCESS_FIELDS = [
    ("pasteurization_applied", "binary", "Pasteurization applied"),
    ("pasteurization_temperature_c", "numeric", "Pasteurization temperature (°C)"),
    ("pasteurization_time_min", "numeric", "Pasteurization time (min)"),
    ("headspace_oxygen_pct", "numeric", "Headspace O₂ (%)"),
    ("headspace_co2_pct", "numeric", "Headspace CO₂ (%)"),
]
CANDIDATE_DESCRIPTOR_FIELDS = [
    ("primary_ingredient_family", "categorical", "Ingredient family"),
    ("ingredient_molecular_weight_g_mol", "numeric", "Molecular weight (g/mol)"),
    ("ingredient_logp", "numeric", "logP"),
    ("ingredient_water_solubility_index", "numeric", "Water-solubility index"),
    ("ingredient_thermal_stability_index", "numeric", "Thermal-stability index"),
    ("ingredient_descriptor_available", "binary", "Descriptor available"),
]
MAX_CANDIDATES = 4
NON_CONTROL_CONTROL_TYPE = "matched_untreated"


def _field_control(field_id: str, kind: str, col: str, value_override: Any = None) -> Any:
    if kind == "categorical":
        opts = SERVICE.schema["categorical_options"].get(col, [])
        default = value_override if value_override is not None else SERVICE.schema.get("categorical_modes", {}).get(col, opts[0] if opts else None)
        return dcc.Dropdown(id=field_id, options=[{"label": o.replace("_", " "), "value": o} for o in opts],
                            value=default, clearable=False, className="dash-dropdown")
    if kind == "binary":
        default_on = value_override if value_override is not None else (1 if SERVICE.schema["numeric_ranges"][col]["median"] >= 0.5 else 0)
        return dcc.Checklist(id=field_id, options=[{"label": " Yes", "value": 1}], value=[1] if default_on else [])
    rng = SERVICE.schema["numeric_ranges"][col]
    default = value_override if value_override is not None else round(rng["median"], 3)
    return dcc.Input(id=field_id, type="number", value=default, className="text-input")


def _shared_required_section() -> html.Div:
    fields = [
        _labeled_field(label, _field_control(f"shared-{col}", kind, col), required=True, error_id=f"shared-{col}-error")
        for col, kind, label in SHARED_REQUIRED_FIELDS
    ]
    return _card(html.Div(fields, className="field-grid"), title="Product & storage conditions", caption="1 · required", icon="fa-cheese")


def _matrix_descriptor_panel() -> html.Details:
    fields = [
        _labeled_field(label, _field_control(f"shared-{col}", kind, col), badge="Auto-filled",
                       source_id=f"shared-{col}-source")
        for col, kind, label in MATRIX_DESCRIPTOR_FIELDS
    ]
    body = [
        html.Div([
            html.Span("Filled from the selected food matrix — every value stays editable.", className="panel-hint"),
            html.Button([_icon("fa-rotate-left"), " Reset to dataset defaults"], id="matrix-reset-btn", n_clicks=0,
                        className="btn btn-tertiary"),
        ], className="panel-hint-row"),
        html.Div(fields, className="field-grid"),
    ]
    return _collapsible("Product descriptors — automatically filled", body)


def _process_panel() -> html.Details:
    fields = [_labeled_field(label, _field_control(f"shared-{col}", kind, col), badge="Optional") for col, kind, label in PROCESS_FIELDS]
    return _collapsible("Advanced processing and atmosphere", html.Div(fields, className="field-grid"))


def _candidate_card(i: int) -> html.Div:
    required_fields = [
        _labeled_field("Treatment type", _field_control(f"cand{i}-treatment_type", "categorical", "treatment_type"),
                       required=True, error_id=f"cand{i}-treatment_type-error"),
        _labeled_field("Ingredient", _field_control(f"cand{i}-primary_ingredient_name", "categorical", "primary_ingredient_name"),
                       required=True, error_id=f"cand{i}-primary_ingredient_name-error"),
        _labeled_field("Concentration", _field_control(f"cand{i}-primary_concentration", "numeric", "primary_concentration"),
                       required=True, error_id=f"cand{i}-primary_concentration-error"),
        _labeled_field("Concentration unit", _field_control(f"cand{i}-primary_concentration_unit", "categorical", "primary_concentration_unit"),
                       required=True, error_id=f"cand{i}-primary_concentration_unit-error"),
    ]
    descriptor_fields = [_labeled_field(label, _field_control(f"cand{i}-{col}", kind, col), badge="Auto-filled")
                         for col, kind, label in CANDIDATE_DESCRIPTOR_FIELDS]
    body = [
        _labeled_field("Candidate name", dcc.Input(id=f"cand{i}-name", type="text", value=f"Candidate {i}", className="text-input"),
                       required=True, error_id=f"cand{i}-name-error"),
        html.Div(required_fields, className="field-grid"),
        _collapsible("Ingredient descriptors — automatically filled", html.Div([
            html.Span("Filled from the selected ingredient — every value stays editable.", className="panel-hint"),
            html.Div(descriptor_fields, className="field-grid"),
        ])),
    ]
    if i > 1:
        body.append(html.Div(html.Button([_icon("fa-xmark"), " Remove candidate"], id=f"cand{i}-remove-btn", n_clicks=0,
                                         className="btn btn-tertiary"), style={"textAlign": "right"}))
    card = _card(html.Div(body), title=f"Candidate {i}")
    return html.Div(card, id=f"cand{i}-wrapper", style={} if i == 1 else {"display": "none"})


def page_prediction_shell() -> html.Div:
    model_options = [{"label": MODEL_LABELS[m], "value": m} for m in CORE_MODELS]
    model_options.append({"label": f"Best validation model ({MODEL_LABELS[SERVICE.best_model]})", "value": BEST_MODEL_KEY})
    return html.Div([
        _page_header("Prediction", "Compare a control formulation against up to four candidate treatments using saved model artifacts."),
        _card(_labeled_field("Model", dcc.Dropdown(id="predict-model-selector", options=model_options,
                                                    value=BEST_MODEL_KEY, clearable=False, className="dash-dropdown"))),
        _shared_required_section(),
        _matrix_descriptor_panel(),
        _process_panel(),
        html.Div([html.Span("2", className="card-number"), html.Span("Candidate treatments (1-4)", className="card-title")],
                 className="section-heading"),
        html.Div([_candidate_card(i) for i in range(1, MAX_CANDIDATES + 1)]),
        html.Button([_icon("fa-plus"), " Add candidate"], id="predict-add-candidate-btn", n_clicks=0, className="btn btn-secondary"),
        html.Div([
            html.Button([_icon("fa-magnifying-glass-chart"), " Predict"], id="predict-run-btn", n_clicks=0,
                       className="btn btn-primary", disabled=False),
        ], style={"textAlign": "right", "margin": "18px 0"}),
        dcc.Loading(html.Div(id="predict-inline-summary")),
        _footer(),
    ])


@callback(
    [Output(f"cand{i}-wrapper", "style") for i in range(2, MAX_CANDIDATES + 1)],
    Input("predict-add-candidate-btn", "n_clicks"),
    [Input(f"cand{i}-remove-btn", "n_clicks") for i in range(2, MAX_CANDIDATES + 1)],
    [State(f"cand{i}-wrapper", "style") for i in range(2, MAX_CANDIDATES + 1)],
    prevent_initial_call=True,
)
def _toggle_candidates(_add, *args):
    n_remove = MAX_CANDIDATES - 1
    styles = list(args[n_remove:])
    trigger = ctx.triggered_id
    visible = [(s or {}).get("display") != "none" for s in styles]
    if trigger == "predict-add-candidate-btn":
        for idx in range(len(visible)):
            if not visible[idx]:
                visible[idx] = True
                break
    else:
        for idx in range(2, MAX_CANDIDATES + 1):
            if trigger == f"cand{idx}-remove-btn":
                visible[idx - 2] = False
    return [{} if v else {"display": "none"} for v in visible]


def _make_matrix_autofill_callback():
    descriptor_ids = [f"shared-{col}" for col, _, _ in MATRIX_DESCRIPTOR_FIELDS]
    source_ids = [f"shared-{col}-source" for col, _, _ in MATRIX_DESCRIPTOR_FIELDS]

    @callback(
        [Output(fid, "value") for fid in descriptor_ids],
        [Output(sid, "children") for sid in source_ids],
        Input("shared-food_matrix", "value"),
        Input("matrix-reset-btn", "n_clicks"),
        [Input(fid, "value") for fid in descriptor_ids],
        prevent_initial_call=True,
    )
    def _autofill(food_matrix, _reset_clicks, *current_values):
        import dash
        trigger = dash.ctx.triggered_id
        lookup = SERVICE.matrix_lookup.get(food_matrix, {})
        if trigger in ("shared-food_matrix", "matrix-reset-btn"):
            values = []
            for col, kind, _ in MATRIX_DESCRIPTOR_FIELDS:
                v = lookup.get(col)
                values.append(([1] if v else []) if kind == "binary" else v)
            sources = ["Dataset default"] * len(descriptor_ids)
            return values + sources
        value_updates = [dash.no_update] * len(descriptor_ids)
        source_updates = [dash.no_update] * len(descriptor_ids)
        for idx, fid in enumerate(descriptor_ids):
            if trigger == fid:
                source_updates[idx] = "User value"
        return value_updates + source_updates
    return _autofill


_matrix_autofill_callback = _make_matrix_autofill_callback()


def _make_ingredient_autofill_callback(i: int):
    descriptor_ids = [f"cand{i}-{col}" for col, _, _ in CANDIDATE_DESCRIPTOR_FIELDS]

    @callback(
        [Output(fid, "value") for fid in descriptor_ids],
        Input(f"cand{i}-primary_ingredient_name", "value"),
        prevent_initial_call=True,
    )
    def _autofill(ingredient_name):
        lookup = SERVICE.ingredient_lookup.get(ingredient_name, dict(NONE_INGREDIENT_DESCRIPTORS))
        values = []
        for col, kind, _ in CANDIDATE_DESCRIPTOR_FIELDS:
            v = lookup.get(col, NONE_INGREDIENT_DESCRIPTORS.get(col))
            values.append(([1] if v else []) if kind == "binary" else v)
        return values
    return _autofill


for _i in range(1, MAX_CANDIDATES + 1):
    _make_ingredient_autofill_callback(_i)

_REQUIRED_SHARED_IDS = [f"shared-{col}" for col, _, _ in SHARED_REQUIRED_FIELDS]
_REQUIRED_CAND_COLS = ["name", "treatment_type", "primary_ingredient_name", "primary_concentration", "primary_concentration_unit"]


def _is_missing(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


@callback(
    Output("predict-run-btn", "disabled"),
    [Output(f"shared-{col}-error", "children") for col, _, _ in SHARED_REQUIRED_FIELDS],
    *[[Output(f"cand{i}-{col}-error", "children") for col in _REQUIRED_CAND_COLS] for i in range(1, MAX_CANDIDATES + 1)],
    [Input(fid, "value") for fid in _REQUIRED_SHARED_IDS],
    *[[Input(f"cand{i}-{col}", "value") for col in _REQUIRED_CAND_COLS] for i in range(1, MAX_CANDIDATES + 1)],
    [State(f"cand{i}-wrapper", "style") for i in range(1, MAX_CANDIDATES + 1)],
)
def _validate_required(*args):
    n_shared = len(_REQUIRED_SHARED_IDS)
    n_cand_cols = len(_REQUIRED_CAND_COLS)
    shared_values = args[:n_shared]
    rest = args[n_shared:]
    cand_blocks = [rest[i * n_cand_cols:(i + 1) * n_cand_cols] for i in range(MAX_CANDIDATES)]
    wrapper_styles = rest[MAX_CANDIDATES * n_cand_cols:]

    any_missing = False
    shared_errors = []
    for val in shared_values:
        missing = _is_missing(val)
        any_missing = any_missing or missing
        shared_errors.append("Required" if missing else "")

    cand_errors_flat: list[str] = []
    for i, block in enumerate(cand_blocks):
        visible = (wrapper_styles[i] or {}).get("display") != "none"
        for val in block:
            missing = visible and _is_missing(val)
            any_missing = any_missing or missing
            cand_errors_flat.append("Required" if missing else "")

    return [any_missing] + shared_errors + cand_errors_flat


def _build_candidate_row(name, treatment_type, ingredient_name, concentration, concentration_unit,
                         ingredient_family, mw, logp, wsi, tsi, desc_avail) -> dict:
    is_none = ingredient_name == "none" or ingredient_name is None
    count = 0 if is_none else 1
    return {
        "name": name, "is_control": 0, "control_type": NON_CONTROL_CONTROL_TYPE,
        "treatment_type": treatment_type,
        "formulation_type": "control" if count == 0 else "single_active",
        "ingredient_count": count,
        "primary_ingredient_name": ingredient_name,
        "primary_ingredient_family": "none" if is_none else ingredient_family,
        "primary_concentration": 0.0 if is_none else concentration,
        "primary_concentration_unit": "none" if is_none else concentration_unit,
        "ingredient_molecular_weight_g_mol": 0.0 if is_none else mw,
        "ingredient_logp": 0.0 if is_none else logp,
        "ingredient_water_solubility_index": 0.0 if is_none else wsi,
        "ingredient_thermal_stability_index": 0.0 if is_none else tsi,
        "ingredient_descriptor_available": 0 if is_none else (1 if desc_avail else 0),
    }


@callback(
    Output("predict-inline-summary", "children"),
    Output("last-prediction-store", "data"),
    Output("url", "pathname", allow_duplicate=True),
    Input("predict-run-btn", "n_clicks"),
    State("predict-model-selector", "value"),
    [State(f"shared-{col}", "value") for col, kind, _ in SHARED_REQUIRED_FIELDS],
    [State(f"shared-{col}", "value") for col, kind, _ in MATRIX_DESCRIPTOR_FIELDS],
    [State(f"shared-{col}", "value") for col, kind, _ in PROCESS_FIELDS],
    *[[
        State(f"cand{i}-name", "value"), State(f"cand{i}-treatment_type", "value"),
        State(f"cand{i}-primary_ingredient_name", "value"),
        State(f"cand{i}-primary_concentration", "value"), State(f"cand{i}-primary_concentration_unit", "value"),
        State(f"cand{i}-primary_ingredient_family", "value"),
        State(f"cand{i}-ingredient_molecular_weight_g_mol", "value"), State(f"cand{i}-ingredient_logp", "value"),
        State(f"cand{i}-ingredient_water_solubility_index", "value"), State(f"cand{i}-ingredient_thermal_stability_index", "value"),
        State(f"cand{i}-ingredient_descriptor_available", "value"),
    ] for i in range(1, MAX_CANDIDATES + 1)],
    [State(f"cand{i}-wrapper", "style") for i in range(1, MAX_CANDIDATES + 1)],
    prevent_initial_call=True,
)
def _run_prediction(n_clicks, model_name, *args):
    import dash
    n_req, n_mat, n_proc = len(SHARED_REQUIRED_FIELDS), len(MATRIX_DESCRIPTOR_FIELDS), len(PROCESS_FIELDS)
    required_vals = args[:n_req]
    rest = args[n_req:]
    matrix_vals = rest[:n_mat]
    rest = rest[n_mat:]
    process_vals = rest[:n_proc]
    rest = rest[n_proc:]

    per_cand_len = 11
    cand_blocks = [rest[i * per_cand_len:(i + 1) * per_cand_len] for i in range(MAX_CANDIDATES)]
    wrapper_styles = rest[MAX_CANDIDATES * per_cand_len:]

    shared: dict[str, Any] = {}
    for (col, kind, _), val in zip(SHARED_REQUIRED_FIELDS, required_vals):
        shared[col] = (1 if val else 0) if kind == "binary" else val
    for (col, kind, _), val in zip(MATRIX_DESCRIPTOR_FIELDS, matrix_vals):
        shared[col] = (1 if val else 0) if kind == "binary" else val
    for (col, kind, _), val in zip(PROCESS_FIELDS, process_vals):
        shared[col] = (1 if val else 0) if kind == "binary" else val

    candidates = []
    for i, block in enumerate(cand_blocks):
        visible = (wrapper_styles[i] or {}).get("display") != "none"
        if not visible:
            continue
        candidates.append(_build_candidate_row(*block))

    if not candidates:
        return _empty_state("fa-triangle-exclamation", "No candidates", "Add at least one candidate before predicting."), dash.no_update, dash.no_update

    result = SERVICE.compare_control_vs_candidates(model_name, shared, candidates)
    top = result["candidates"][0]
    summary = _card(html.Div([
        _kpi_grid(
            _kpi("Control shelf life", f"{result['control']['prediction_days']:.1f} d", "fa-flask", TEXT_MUTED),
            _kpi("Best candidate", f"{top['predicted_candidate_shelf_life']:.1f} d", "fa-trophy", GOOD, sub=top["candidate_name"]),
            _kpi("90% interval (best)", f"{top['lower_bound']:.1f} – {top['upper_bound']:.1f} d", "fa-arrows-left-right-to-line", BLUE_ACCENT),
        ),
        html.Div(html.A([_icon("fa-ranking-star"), " View full results"], href="/results", className="btn btn-primary"),
                 style={"textAlign": "right", "marginTop": "8px"}),
    ]), title="Instant prediction", icon="fa-bolt")
    return summary, result, "/results"


# ── Page: Results ────────────────────────────────────────────────────────────

def page_results(store_data: dict | None) -> html.Div:
    if not store_data:
        return html.Div([
            _page_header("Results", "Ranked candidate comparison from your most recent prediction."),
            _card(_empty_state("fa-flask", "No prediction yet", "Go to the Prediction page, fill in a control and at least one candidate, then click Predict."), title=None),
            _footer(),
        ])

    control = store_data["control"]
    cands = store_data["candidates"]
    kpis = _kpi_grid(
        _kpi("Control shelf life", f"{control['prediction_days']:.1f} d", "fa-flask", TEXT_MUTED),
        _kpi("Best candidate", f"{cands[0]['predicted_candidate_shelf_life']:.1f} d", "fa-trophy", GOOD, sub=cands[0]["candidate_name"]),
        _kpi("Best improvement", f"{cands[0]['absolute_improvement_days']:+.1f} d", "fa-arrow-trend-up", MAROON,
             sub=f"{cands[0]['relative_improvement_pct']:+.1f}%" if not np.isnan(cands[0]["relative_improvement_pct"]) else "n/a"),
    )
    rows = []
    for c in cands:
        rows.append([
            c["candidate_name"], c["model_label"], f"{c['predicted_candidate_shelf_life']:.1f}",
            f"{c['predicted_control_shelf_life']:.1f}", f"{c['absolute_improvement_days']:+.1f}",
            f"{c['relative_improvement_pct']:+.1f}%" if not np.isnan(c["relative_improvement_pct"]) else "n/a",
            f"{c['shelf_life_ratio']:.2f}" if not np.isnan(c["shelf_life_ratio"]) else "n/a",
            c["rank"], f"{c['lower_bound']:.1f}", f"{c['upper_bound']:.1f}",
        ])
    table = _card(_table(
        ["Candidate", "Model", "Predicted (d)", "Control (d)", "Δ days", "Δ %", "Ratio", "Rank", "Lower 90%", "Upper 90%"], rows,
    ), title="Ranked candidates", icon="fa-ranking-star")

    names = ["Control"] + [c["candidate_name"] for c in cands]
    values = [control["prediction_days"]] + [c["predicted_candidate_shelf_life"] for c in cands]
    bar = go.Figure(go.Bar(x=names, y=values, marker_color=[TEXT_MUTED] + [MAROON] * len(cands)))
    _style_fig(bar, height=320, title="Control vs. candidates", showlegend=False)

    rank_fig = go.Figure(go.Bar(x=[c["candidate_name"] for c in cands], y=[c["predicted_candidate_shelf_life"] for c in cands], marker_color=BLUE_ACCENT))
    _style_fig(rank_fig, height=300, title="Candidate ranking", showlegend=False)

    impr_fig = go.Figure(go.Bar(x=[c["candidate_name"] for c in cands], y=[c["absolute_improvement_days"] for c in cands],
                                marker_color=[GOOD if c["absolute_improvement_days"] >= 0 else CRITICAL for c in cands]))
    _style_fig(impr_fig, height=300, title="Improvement vs. control (days)", showlegend=False)

    return html.Div([
        _page_header("Results", "Ranked candidate comparison from your most recent prediction."),
        kpis, table,
        html.Div([_card(_graph(bar)), _card(_graph(rank_fig)), _card(_graph(impr_fig))], className="row-flex"),
        _footer(),
    ])


# ── Page: How it works ───────────────────────────────────────────────────────

FEATURE_GLOSSARY = [
    ("food_matrix", "The specific cheese product (e.g. mozzarella, burrata)."),
    ("matrix_ph", "Acidity of the product — lower values generally slow microbial growth."),
    ("matrix_water_activity", "Free water available for microbial growth; a key spoilage driver."),
    ("storage_temperature_c", "Storage/display temperature — the single strongest lever on shelf life."),
    ("packaging_type", "Barrier properties of the packaging (vacuum, MAP, active film, etc.)."),
    ("indicator_type", "The spoilage indicator organism/measure the threshold is defined against."),
    ("indicator_threshold_log_cfu_g", "The count level (log CFU/g) that defines end-of-shelf-life."),
    ("primary_ingredient_name", "The active antimicrobial/antioxidant ingredient, if any, added to the formulation."),
]


def page_how_it_works() -> html.Div:
    steps = [
        ("fa-database", "Data curation", "Load the training workbook, drop identifiers and provenance flags so they can never leak into a prediction."),
        ("fa-clipboard-check", "Schema validation", "Automatically classify every remaining column as numeric, binary, or categorical."),
        ("fa-table-cells", "Feature preparation", "Median/mode imputation, one-hot encoding for tree models, scaling for the LSTM, native dtypes preserved for the EBM."),
        ("fa-brain", "Model training", "Fit five independent models on the same context-grouped train split, with early stopping where supported."),
        ("fa-chart-line", "Prediction", "Load the saved pipelines and predict a control plus up to four candidates — never retrains."),
        ("fa-lightbulb", "Explainability", "Permutation importance for every model, native importance where available, EBM shape functions, and local factors for your last prediction."),
    ]
    step_cards = html.Div([
        _card(html.Div([
            html.Div(_icon(icon), className="pipeline-icon"),
            html.Div(title, className="pipeline-title"),
            html.Div(desc, className="pipeline-desc"),
        ]), title=None)
        for icon, title, desc in steps
    ], className="row-flex row-flex-3")

    model_cards = html.Div([
        _card(html.Div([
            html.Div(MODEL_LABELS[m], className="model-card-title"),
            html.Div(MODEL_BLURBS[m], className="model-card-desc"),
        ]))
        for m in CORE_MODELS
    ], className="row-flex row-flex-5")

    glossary_rows = [[c, desc] for c, desc in FEATURE_GLOSSARY]
    glossary = _card(_table(["Feature", "Meaning"], glossary_rows), title="Feature glossary (selected)", icon="fa-book-open")

    tips = _card(html.Ul([
        html.Li("This dataset is ~99.6% scientifically-constrained synthetic data with a 36-row real, paper-derived subset — treat absolute predictions as a prototyping signal, not a validated lab result."),
        html.Li("The 90% interval on every prediction comes from split-conformal calibration on the validation set, not from the model itself."),
        html.Li("The LSTM is included as an experimental benchmark only; this data is cross-sectional, not sequential, and the LSTM has no natural advantage here."),
        html.Li("Retraining only happens via `python train_models.py` from the command line — this dashboard only ever reads saved artifacts."),
    ]), title="Good to know", icon="fa-circle-info")

    return html.Div([
        _page_header("How Shelf-Life Studio Works", "From raw workbook to an explainable, ranked shelf-life prediction."),
        step_cards,
        _card(model_cards, title="Models used", icon="fa-microchip"),
        glossary,
        tips,
        _footer(),
    ])


# ── Page: References ─────────────────────────────────────────────────────────

def page_references() -> html.Div:
    df = SERVICE.full_df
    real = df[df["data_origin"] == "real_paper_derived"]
    grouped = real.groupby("source_link").agg(rows=("row_id", "count"), food_matrices=("food_matrix", lambda s: ", ".join(sorted(s.unique()))))
    grouped = grouped.sort_values("rows", ascending=False).reset_index()

    rows = [[html.A(link, href=link, target="_blank", rel="noopener"), fm, n] for link, fm, n in
            zip(grouped["source_link"], grouped["food_matrices"], grouped["rows"])]
    ref_table = _card(_table(["Source (DOI)", "Food matrix", "Rows"], rows),
                      title="Real, paper-derived data sources", caption=f"{len(grouped)} studies backing {len(real)} rows", icon="fa-book")

    method_card = _card(html.P(
        "The remaining "
        f"{len(df) - len(real):,} rows use "
        f"{df.loc[df['data_origin'] != 'real_paper_derived', 'augmentation_method'].mode().iat[0].replace('_', ' ')}"
        " — synthetic points sampled within scientifically plausible bounds derived from the same literature, "
        "not measured directly. Every row's data_origin is excluded from the model's own features."
    ), title="Synthetic data methodology", icon="fa-flask-vial")

    return html.Div([
        _page_header("References", "The literature backing the real subset of this dataset, plus how the synthetic majority was generated."),
        ref_table, method_card,
        _footer(),
    ])


# ── Routing ──────────────────────────────────────────────────────────────────

@callback(Output("page-content", "children"), Input("url", "pathname"), State("last-prediction-store", "data"))
def render_page(pathname: str, store_data):
    pathname = pathname or "/"
    if pathname == "/datasets":
        return page_datasets()
    if pathname == "/modeling":
        return page_modeling()
    if pathname == "/prediction":
        return page_prediction_shell()
    if pathname == "/results":
        return page_results(store_data)
    if pathname == "/explainability":
        return page_explainability_shell()
    if pathname == "/how-it-works":
        return page_how_it_works()
    if pathname == "/references":
        return page_references()
    return page_home()


if __name__ == "__main__":
    app.run(debug=True, dev_tools_ui=False, host="127.0.0.1", port=8050)
