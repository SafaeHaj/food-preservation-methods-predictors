"""
FastAPI backend for Shelf-Life Studio's React frontend.

This is a thin JSON wrapper around model_service.py -- it does not
reimplement any modeling, preprocessing, or prediction logic. Every number
returned here comes from the exact same ModelService the previous Dash
frontend (app.py) used, loaded once at startup from the saved artifacts.
NEVER retrains; NEVER touches train_models.py.

Usage:
    uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from model_service import BEST_MODEL_KEY, MODEL_LABELS, NONE_INGREDIENT_DESCRIPTORS, ModelService, build_candidate_row, build_candidate_row_v6
from classification_service import CLF_MODEL_LABELS, ClassificationService
from ingredient_ranking_service import IngredientRankingService
from specialist_registry import SpecialistRegistry
from backend.assistant import AssistantService
from backend.auth import router as auth_router
from backend.db import init_db

SERVICE = ModelService()
CORE_MODELS = [m for m in ("random_forest", "lightgbm", "xgboost", "ebm", "lstm") if m in SERVICE.models]
ASSISTANT = AssistantService(SERVICE)

# The classifier and the ingredient ranking are each separate,
# independently-trained artifact sets (artifacts_classification/,
# artifacts_ingredient_ranking/) that may not exist yet on a given checkout
# -- load defensively so a missing/partial build never takes down the
# (unrelated) regression API.
try:
    CLF_SERVICE: ClassificationService | None = ClassificationService()
except FileNotFoundError:
    CLF_SERVICE = None

try:
    ING_SERVICE: IngredientRankingService | None = IngredientRankingService()
except FileNotFoundError:
    ING_SERVICE = None

# V6 specialist architecture: routes by cheese_category + model_task instead
# of a single global model set. Loaded defensively the same way -- a missing
# artifacts_v6/ tree degrades this feature only, never the rest of the app.
try:
    SPECIALIST_REGISTRY: SpecialistRegistry | None = SpecialistRegistry()
except FileNotFoundError:
    SPECIALIST_REGISTRY = None

init_db()

MODEL_BLURBS = {
    "random_forest": "Bagged ensemble of decision trees; robust baseline, resistant to overfitting.",
    "lightgbm": "Gradient-boosted trees optimized for speed on tabular data.",
    "xgboost": "Gradient-boosted trees with regularization; strong general-purpose accuracy.",
    "ebm": "Generalized additive model with pairwise interactions; every prediction fully decomposable.",
    "lstm": "Recurrent network run on the feature vector as an artificial sequence -- an experimental benchmark, not a natural fit for this cross-sectional data.",
}

CLF_MODEL_BLURBS = {
    "random_forest": "Bagged ensemble of decision trees; class-balanced to avoid over-favoring the majority class.",
    "xgboost": "Gradient-boosted trees; typically the sharper decision boundary of the two classifiers.",
}

app = FastAPI(title="Shelf-Life Studio API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    # Required for the httpOnly session cookie to travel on cross-origin XHR
    # (the frontend is a different port, so every API call is cross-origin).
    # Note allow_credentials forbids a wildcard origin -- the explicit list above
    # is load-bearing, not just tidiness.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


def _clean(obj: Any) -> Any:
    """Recursively replace NaN/inf with None so FastAPI's default JSON
    encoder (strict JSON, unlike Python's json module) never chokes."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
        return None
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if (np.isnan(v) or np.isinf(v)) else v
    if isinstance(obj, (np.integer,)):
        return int(obj)
    return obj


# ── Health / manifest / schema ──────────────────────────────────────────────

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "best_model": SERVICE.best_model, "models": CORE_MODELS}


@app.get("/api/manifest")
def manifest() -> dict:
    return _clean({**SERVICE.manifest, "n_contexts_total": int(SERVICE.full_df["context_id"].nunique())})


@app.get("/api/schema")
def schema() -> dict:
    return _clean(SERVICE.schema)


@app.get("/api/lookups/matrix")
def matrix_lookup() -> dict:
    return _clean(SERVICE.matrix_lookup)


@app.get("/api/lookups/ingredient")
def ingredient_lookup() -> dict:
    return _clean(SERVICE.ingredient_lookup)


# ── Dataset workspaces (synthetic / real) ───────────────────────────────────

def _schema_preview(df: pd.DataFrame) -> list[dict]:
    rows = []
    for c in SERVICE.feature_cols:
        kind = "numeric" if c in SERVICE.numeric_cols else ("binary" if c in SERVICE.binary_cols else "categorical")
        miss_pct = float(df[c].isna().mean() * 100)
        example = df[c].dropna().iloc[0] if df[c].notna().any() else None
        rows.append({"column": c, "role": kind, "dtype": str(df[c].dtype), "missing_pct": miss_pct, "example": _clean(example)})
    return rows


@app.get("/api/dataset/synthetic")
def dataset_synthetic() -> dict:
    df = SERVICE.full_df
    real = df[df["data_origin"] == "real_paper_derived"]
    synth = df[df["data_origin"] != "real_paper_derived"]
    temp_hist_counts, temp_hist_edges = np.histogram(synth["storage_temperature_c"], bins=16)
    return _clean({
        "total_rows": len(synth),
        "contexts": int(synth["context_id"].nunique()),
        "controls": int((synth["is_control"] == 1).sum()),
        "treatments": int((synth["is_control"] == 0).sum()),
        "target_min": float(synth["shelf_life_days"].min()),
        "target_max": float(synth["shelf_life_days"].max()),
        "ingredient_families": synth[synth["primary_ingredient_family"] != "none"]["primary_ingredient_family"].value_counts().to_dict(),
        "storage_temperature_histogram": temp_hist_counts.tolist(),
        "storage_temperature_bin_edges": temp_hist_edges.tolist(),
        "shelf_life_histogram": np.histogram(synth["shelf_life_days"], bins=24)[0].tolist(),
        "shelf_life_bin_edges": np.histogram(synth["shelf_life_days"], bins=24)[1].tolist(),
        "generation_method": synth["data_origin"].mode().iat[0] if len(synth) else None,
        "has_real_subset": len(real) > 0,
        "schema_preview": _schema_preview(df)[:12],
    })


@app.get("/api/dataset/real")
def dataset_real() -> dict:
    """This dataset version is 100% synthetic (data_origin has a single
    value) -- there is no real, paper-derived subset to report. Reported
    honestly as zero rather than fabricated. The generation-rule breakdown
    (source_rule_id) is real, useful provenance info in its place."""
    df = SERVICE.full_df
    real = df[df["data_origin"] == "real_paper_derived"]
    rule_counts = df["source_rule_id"].value_counts().to_dict() if "source_rule_id" in df.columns else {}
    return _clean({
        "total_rows": len(real),
        "has_real_subset": len(real) > 0,
        "source_studies": [],
        "generation_rules": rule_counts,
        "quality_flags": df["quality_flag"].value_counts().to_dict(),
        "food_matrices": real["food_matrix"].value_counts().to_dict() if len(real) else {},
        "provenance_note": "This dataset version is entirely synthetic (data_origin is constant) -- there is no real, paper-derived subset. Every row's data_origin/quality_flag/training_weight/source_rule_id is excluded from model features to prevent leakage.",
    })


# ── Modeling ─────────────────────────────────────────────────────────────────

@app.get("/api/models")
def list_models() -> dict:
    ranked = sorted(CORE_MODELS, key=lambda m: SERVICE.metrics[m]["validation_rmse"])
    rows = []
    for m in ranked:
        met = SERVICE.metrics[m]
        rows.append({
            "id": m, "label": MODEL_LABELS[m], "blurb": MODEL_BLURBS[m],
            "is_best": m == SERVICE.best_model,
            "validation_r2": met["validation_r2"], "test_r2": met["test_r2"],
            "validation_rmse": met["validation_rmse"], "test_rmse": met["test_rmse"],
            "validation_mae": met["validation_mae"], "test_mae": met["test_mae"],
            "training_duration_sec": met["training_duration_sec"],
            "n_trainable_params": met.get("n_trainable_params"),
        })
    return _clean({
        "best_model": SERVICE.best_model,
        "models": rows,
        "manifest": SERVICE.manifest,
    })


@app.get("/api/models/{model}/details")
def model_details(model: str) -> dict:
    if model not in SERVICE.metrics:
        raise HTTPException(404, f"Unknown model: {model}")
    m = SERVICE.metrics[model]
    preds = SERVICE.predictions.query("model == @model")
    scatter = {
        split: preds[preds["split"] == split][["y_true", "y_pred"]].to_dict("records")
        for split in ("train", "validation", "test")
    }
    return _clean({
        "id": model, "label": MODEL_LABELS[model],
        "metrics": m,
        "curves": SERVICE.curves.get(model),
        "feature_importance": SERVICE.feature_importance.get(model, {}),
        "category_errors": SERVICE.category_errors.get(model, {}),
        "scatter": scatter,
    })


@app.get("/api/models/ebm/shapes")
def ebm_shapes(top_n: int = 4) -> dict:
    """EBM global shape functions for its top terms (by native importance),
    excluding pairwise-interaction terms. Same source data the previous Dash
    app's EBM shape-function charts used (ebm_model.explain_global())."""
    if "ebm" not in SERVICE.models:
        raise HTTPException(404, "EBM model not available")
    native = SERVICE.feature_importance.get("ebm", {}).get("native", {})
    top_terms = sorted(native.items(), key=lambda kv: abs(kv[1]), reverse=True)[:top_n]
    ebm_model = SERVICE.models["ebm"]
    global_exp = ebm_model.explain_global()
    names = list(global_exp.data()["names"])
    shapes = []
    for term, _ in top_terms:
        if term not in names:
            continue
        idx = names.index(term)
        d = global_exp.data(idx)
        shapes.append({
            "term": term,
            "type": d["type"],
            "names": [str(x) for x in d["names"]],
            "scores": [float(s) for s in d["scores"]],
        })
    return _clean({"shapes": shapes})


# ── Prediction ───────────────────────────────────────────────────────────────

class Candidate(BaseModel):
    name: str
    treatment_type: str
    application_method: str
    primary_ingredient_name: str
    primary_concentration: float
    primary_concentration_unit: str
    primary_ingredient_family: Optional[str] = None


class PredictRequest(BaseModel):
    model: str
    shared: dict[str, Any]
    candidates: list[Candidate]


@app.post("/api/predict")
def predict(req: PredictRequest) -> dict:
    if not req.candidates:
        raise HTTPException(400, "At least one candidate is required")
    try:
        candidates = [build_candidate_row(c.model_dump()) for c in req.candidates]
        result = SERVICE.compare_control_vs_candidates(req.model, req.shared, candidates)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return _clean(result)


class ExplainRequest(BaseModel):
    model: str
    row: dict[str, Any]
    top_k: int = 8


@app.post("/api/explain/local")
def explain_local(req: ExplainRequest) -> dict:
    try:
        factors = SERVICE.local_explanation(req.model, req.row, top_k=req.top_k)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return _clean({"factors": factors})


# ── Assistant ────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class AssistantChatRequest(BaseModel):
    messages: list[ChatMessage]
    page_context: Optional[dict[str, Any]] = None


@app.post("/api/assistant/chat")
def assistant_chat(req: AssistantChatRequest) -> dict:
    if not req.messages:
        raise HTTPException(400, "At least one message is required")
    try:
        result = ASSISTANT.chat(
            [m.model_dump() for m in req.messages],
            page_context=req.page_context,
        )
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc
    return _clean(result)


# ── References ───────────────────────────────────────────────────────────────

@app.get("/api/references")
def references() -> dict:
    """This dataset version has no real, paper-derived rows and no DOI-linked
    source_link column -- data_origin is constant (synthetic_literature_constrained)
    and provenance is instead tracked per-row via source_rule_id, a generation
    rule tag (e.g. RULE_ESSENTIAL_OIL), not a citation. Reported honestly."""
    return _clean(SERVICE.dataset_references())


# ── V6 specialist architecture (cheese_category x model_task routing) ──────
#
# Additive to the /api/predict path above: routes each prediction to the
# correct specialist (soft/semi_hard/hard) and task (general_shelf_life vs
# safety_endpoint) via SpecialistRegistry, never lets the caller pick a
# model, and always reports routing_meta (reduced_support/reason) so a
# thin-sample or fallback-routed prediction is never presented with the same
# confidence as a fully-supported one.

def _require_v6() -> SpecialistRegistry:
    if SPECIALIST_REGISTRY is None:
        raise HTTPException(503, "V6 specialist artifacts not found. Run `python train_specialists.py` first.")
    return SPECIALIST_REGISTRY


@app.get("/api/v6/health")
def v6_health() -> dict:
    if SPECIALIST_REGISTRY is None:
        return {"available": False}
    loaded = {
        f"{cat}/{task}": svc is not None
        for cat, tasks in SPECIALIST_REGISTRY.services.items()
        for task, svc in tasks.items()
    }
    return {"available": True, "specialists": loaded}


@app.get("/api/v6/cheese-catalog")
def cheese_catalog_v6() -> dict:
    reg = _require_v6()
    return _clean({"catalog": reg.cheese_catalog})


@app.get("/api/v6/routing")
def routing_v6(category: str) -> dict:
    """Single authoritative indicator_type -> model_task mapping for a
    category (SpecialistRegistry.indicator_task_map). The frontend fetches
    this instead of independently re-deriving the same scientific routing
    rule from two merged schemas -- one source of truth, per audit item #8."""
    reg = _require_v6()
    if category not in reg.services:
        raise HTTPException(404, f"Unknown cheese_category: {category!r}")
    return {"category": category, "indicator_task_map": reg.indicator_task_map(category)}


@app.get("/api/v6/schema")
def schema_v6(category: str, task: str) -> dict:
    reg = _require_v6()
    svc, routing_meta = reg.resolve(category, task)
    if svc is None:
        raise HTTPException(404, routing_meta["reason"] or "No specialist available")
    return _clean({**svc.schema, "routing": routing_meta, "best_model": svc.best_model, "model_label": MODEL_LABELS.get(svc.best_model, svc.best_model)})


class CandidateV6(BaseModel):
    name: str
    treatment_type: str
    application_method: str
    primary_ingredient_name: str
    primary_concentration: float
    primary_concentration_unit: str
    primary_ingredient_family: Optional[str] = None


class PredictV6Request(BaseModel):
    cheese_category: str
    model_task: str
    shared: dict[str, Any]
    candidates: list[CandidateV6]


@app.post("/api/v6/predict")
def predict_v6(req: PredictV6Request) -> dict:
    reg = _require_v6()
    if not req.candidates:
        raise HTTPException(400, "At least one candidate is required")

    # Hard-fail cases only: specialist genuinely unavailable, or physical_form
    # missing (must never be silently guessed -- audit item #4). Everything
    # else (unseen categoricals, numeric extrapolation, weak-but-present
    # physical-form support) still predicts, but the response's `support`
    # field carries an explicit, structured level the UI must not present as
    # a normal high-confidence result (audit item #6).
    support = reg.assess_prediction_support(req.cheese_category, req.model_task, req.shared)
    if not support["can_predict"]:
        status = 503 if support["level"] == "unavailable" else 400
        raise HTTPException(status, support["reason"])

    svc, routing_meta = reg.resolve(req.cheese_category, req.model_task)
    try:
        candidates = [build_candidate_row_v6(c.model_dump()) for c in req.candidates]
        result = svc.compare_control_vs_candidates(svc.best_model, req.shared, candidates)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    result["routing"] = routing_meta
    result["support"] = support
    result["model_label"] = MODEL_LABELS.get(svc.best_model, svc.best_model)
    return _clean(result)


class ExplainV6Request(BaseModel):
    cheese_category: str
    model_task: str
    row: dict[str, Any]
    top_k: int = 8


@app.post("/api/v6/explain/local")
def explain_local_v6(req: ExplainV6Request) -> dict:
    reg = _require_v6()
    svc, routing_meta = reg.resolve(req.cheese_category, req.model_task)
    if svc is None:
        raise HTTPException(503, routing_meta["reason"] or "No specialist model available for this cheese category/task")
    try:
        factors = svc.local_explanation(svc.best_model, req.row, top_k=req.top_k)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return _clean({"factors": factors, "routing": routing_meta})


# ── Classification (formulation+treatment efficacy class) ──────────────────
#
# Independent of the regression models above: reads only from
# artifacts_classification/ (produced by train_classifier.py), a separate
# artifact set from the regression pipeline's artifacts/. Predicts a
# discrete efficacy class (Low / Medium / High shelf-life improvement over a
# matched control) for a full formulation+treatment combination -- not a
# per-ingredient label -- because the training data shows the same
# ingredient's effect varies substantially with matrix, concentration, and
# application method (see class_distribution.json's by_ingredient_family
# breakdown for the evidence).

def _require_clf() -> ClassificationService:
    if CLF_SERVICE is None:
        raise HTTPException(503, "Classification artifacts not found. Run `python train_classifier.py` first.")
    return CLF_SERVICE


@app.get("/api/classification/health")
def classification_health() -> dict:
    if CLF_SERVICE is None:
        return {"available": False}
    return {"available": True, "best_model": CLF_SERVICE.best_model, "models": CLF_SERVICE.available_models}


@app.get("/api/classification/manifest")
def classification_manifest() -> dict:
    svc = _require_clf()
    return _clean({**svc.manifest, "class_definitions": svc.class_definitions})


@app.get("/api/classification/schema")
def classification_schema() -> dict:
    svc = _require_clf()
    return _clean(svc.schema)


@app.get("/api/classification/distribution")
def classification_distribution() -> dict:
    svc = _require_clf()
    return _clean(svc.class_distribution)


@app.get("/api/classification/models")
def classification_models() -> dict:
    svc = _require_clf()
    ranked = sorted(svc.available_models, key=lambda m: svc.metrics[m]["test"]["macro_f1"], reverse=True)
    rows = []
    for m in ranked:
        met = svc.metrics[m]
        rows.append({
            "id": m, "label": CLF_MODEL_LABELS.get(m, m), "blurb": CLF_MODEL_BLURBS.get(m, ""),
            "is_best": m == svc.best_model,
            "test_accuracy": met["test"]["accuracy"], "test_macro_f1": met["test"]["macro_f1"],
            "validation_accuracy": met["validation"]["accuracy"], "validation_macro_f1": met["validation"]["macro_f1"],
            "training_duration_sec": met["training_duration_sec"],
        })
    return _clean({
        "best_model": svc.best_model,
        "models": rows,
        "manifest": svc.manifest,
        "class_definitions": svc.class_definitions,
    })


@app.get("/api/classification/models/{model}/details")
def classification_model_details(model: str) -> dict:
    svc = _require_clf()
    if model not in svc.metrics:
        raise HTTPException(404, f"Unknown classifier: {model}")
    return _clean({
        "id": model, "label": CLF_MODEL_LABELS.get(model, model),
        "metrics": svc.metrics[model],
        "confusion_matrix": svc.confusion.get(model),
        "feature_importance": svc.feature_importance.get(model, {}),
    })


class ClassificationCandidate(BaseModel):
    name: str
    treatment_type: str
    application_method: str
    primary_ingredient_name: str
    primary_concentration: float
    primary_concentration_unit: str
    primary_ingredient_family: Optional[str] = None


class ClassificationPredictRequest(BaseModel):
    model: str
    shared: dict[str, Any]
    candidates: list[ClassificationCandidate]


@app.post("/api/classification/predict")
def classification_predict(req: ClassificationPredictRequest) -> dict:
    svc = _require_clf()
    if not req.candidates:
        raise HTTPException(400, "At least one candidate is required")
    try:
        rows = [{**req.shared, **build_candidate_row(c.model_dump())} for c in req.candidates]
        results = svc.predict_many(req.model, rows)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return _clean({"results": results, "class_definitions": svc.class_definitions})


# ── Ingredient efficacy ranking ─────────────────────────────────────────────
#
# A third, independent system from both the regression models above and the
# formulation classifier: ranks individual INGREDIENTS by their typical
# efficacy across every context they were tested in, controlling for that
# context via a regression-adjusted effect (see train_ingredient_ranking.py
# for the full methodology). There is nothing to predict per-request here --
# the ranking is a fixed table computed once from the training data, so
# these endpoints are read-only lookups over artifacts_ingredient_ranking/.

def _require_ing() -> IngredientRankingService:
    if ING_SERVICE is None:
        raise HTTPException(503, "Ingredient ranking artifacts not found. Run `python train_ingredient_ranking.py` first.")
    return ING_SERVICE


@app.get("/api/ingredients/health")
def ingredients_health() -> dict:
    return {"available": ING_SERVICE is not None}


@app.get("/api/ingredients/manifest")
def ingredients_manifest() -> dict:
    svc = _require_ing()
    return _clean({**svc.manifest, "class_definitions": svc.class_definitions})


@app.get("/api/ingredients/rankings")
def ingredients_rankings() -> dict:
    svc = _require_ing()
    return _clean({"rankings": svc.rankings, "families": svc.families, "class_definitions": svc.class_definitions})


@app.get("/api/ingredients/rankings/{name}")
def ingredient_detail(name: str) -> dict:
    svc = _require_ing()
    row = svc.get(name)
    if row is None:
        raise HTTPException(404, f"Unknown ingredient: {name}")
    return _clean(row)
