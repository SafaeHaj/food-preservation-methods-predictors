"""
Backend tools exposed to the LLM. Every tool is a thin wrapper around
ModelService (the same object backend/main.py serves REST endpoints from) --
no tool re-implements modeling/statistics logic, and no tool result is
touched by the LLM before being returned to the user as a "fact"; the LLM
only narrates numbers these functions actually computed.
"""
from __future__ import annotations

from typing import Any, Callable

from model_service import ModelService, build_candidate_row

PROJECT_OVERVIEW = {
    "name": "Shelf-Life Studio",
    "purpose": (
        "A McGill Food Science research platform that predicts cheese shelf life "
        "(shelf_life_days) from formulation, processing, packaging, and storage "
        "conditions, and lets researchers compare how antimicrobial/antioxidant "
        "treatments extend shelf life relative to an untreated control."
    ),
    "pipeline": [
        "1. Data: a single workbook (data/raw/CHEESE_SHELF_LIFE_REVISED_READY_TO_TRAIN.xlsx, "
        "sheet 'training_data') of synthetic, literature- and database-constrained cheese "
        "formulation rows.",
        "2. Split: rows are grouped by context_id and split 70/15/15 into train/validation/test "
        "so no context (a formulation + its control) is ever divided across splits (leakage-safe).",
        "3. Features: matrix descriptors (pH, water activity, moisture/fat/protein/salt %, "
        "ripening days), storage conditions (temperature, packaging, headspace gas), the "
        "antimicrobial/antioxidant treatment (type, application method, ingredient, "
        "concentration), and the spoilage indicator being tracked. Identifier columns "
        "(row_id, context_id, formulation_id, source_rule_id) and provenance columns "
        "(data_origin, training_weight, quality_flag) are excluded from features -- they "
        "describe the row's lineage, not the product, and would leak trivially.",
        "4. Models: four independently trained regressors -- Random Forest, LightGBM, "
        "XGBoost, and an Explainable Boosting Machine (EBM) -- plus an experimental LSTM "
        "benchmark when available. Selected by lowest validation RMSE.",
        "5. Explainability: EBM ships native global/local decompositions; other models use "
        "permutation importance and reference-value perturbation for local explanations.",
        "6. Serving: a FastAPI backend (model_service.ModelService) loads the saved artifacts "
        "once and serves prediction/comparison/explanation/leaderboard endpoints to a Next.js "
        "frontend. Nothing is retrained at request time.",
    ],
    "target_variable": "shelf_life_days (days until the cheese formulation is predicted to spoil under the given storage/packaging conditions)",
}

FEATURE_GLOSSARY: dict[str, str] = {
    "food_matrix": "The specific cheese product (e.g. 'gouda_cheese', 'brie_cheese') the row describes.",
    "cheese_category": "Broad texture category of the cheese: hard, semi_hard, or soft.",
    "matrix_ph": "pH of the cheese matrix; lower pH generally slows microbial spoilage.",
    "matrix_water_activity": "Water activity (aw), 0-1 scale; the fraction of water available for microbial growth. Lower aw extends shelf life.",
    "matrix_moisture_pct": "Moisture content of the cheese, percent by weight.",
    "matrix_fat_pct": "Fat content of the cheese, percent by weight.",
    "matrix_protein_pct": "Protein content of the cheese, percent by weight.",
    "matrix_salt_pct": "Salt (NaCl) content of the cheese, percent by weight; salt is itself a preservative.",
    "matrix_ripening_days": "Days the cheese was ripened/aged before the shelf-life clock in this row starts.",
    "pasteurization_applied": "1 if the milk was pasteurized before cheesemaking, else 0.",
    "storage_temperature_c": "Storage temperature in degrees Celsius during the shelf-life trial.",
    "packaging_type": "Packaging format used (e.g. vacuum, modified-atmosphere, wax-coated).",
    "headspace_oxygen_pct": "Oxygen percent in the package headspace gas mix.",
    "headspace_co2_pct": "CO2 percent in the package headspace gas mix.",
    "headspace_n2_pct": "Nitrogen percent in the package headspace gas mix.",
    "indicator_group": "Broad category of the spoilage indicator being monitored (e.g. microbial, chemical, sensory).",
    "indicator_type": "Specific spoilage indicator tracked to define end-of-shelf-life (e.g. a mold count, a TVB-N threshold).",
    "indicator_threshold": "The indicator value at which the product is considered spoiled/end-of-shelf-life.",
    "indicator_unit": "Unit of the indicator_threshold value.",
    "initial_indicator_value": "The indicator's value at time zero (start of storage).",
    "is_control": "1 if this row is the untreated control for its context_id, 0 if it is a treatment.",
    "treatment_type": "Category of intervention applied (e.g. antimicrobial, antioxidant, none for controls).",
    "application_method": "How the treatment was applied (e.g. direct addition, coating, packaging-incorporated).",
    "ingredient_count": "Number of active ingredients in the treatment (0 for controls/no treatment).",
    "primary_ingredient_name": "Name of the main active ingredient used in the treatment ('none' for controls).",
    "primary_ingredient_family": "Chemical/functional family of the primary ingredient (e.g. essential oil, organic acid).",
    "primary_concentration": "Dose of the primary ingredient applied.",
    "primary_concentration_unit": "Unit of primary_concentration (e.g. %, ppm, mg/kg).",
    "shelf_life_days": "TARGET. Predicted/observed days until the product reaches its spoilage indicator threshold.",
}


def _get_service(services: dict[str, Any]) -> ModelService:
    return services["model_service"]


def tool_get_project_overview(services: dict[str, Any], **_: Any) -> dict[str, Any]:
    svc = _get_service(services)
    return {
        **PROJECT_OVERVIEW,
        "best_model": svc.best_model,
        "available_models": svc.available_models,
        "n_training_rows": len(svc.full_df),
        "n_contexts": int(svc.full_df["context_id"].nunique()),
    }


def tool_get_dataset_statistics(services: dict[str, Any], cheese_category: str | None = None, **_: Any) -> dict[str, Any]:
    return _get_service(services).dataset_statistics(cheese_category=cheese_category)


def tool_get_feature_information(services: dict[str, Any], feature_name: str | None = None, **_: Any) -> dict[str, Any]:
    svc = _get_service(services)
    if feature_name:
        if feature_name not in FEATURE_GLOSSARY:
            return {"error": f"Unknown feature: {feature_name!r}", "known_features": sorted(FEATURE_GLOSSARY)}
        info: dict[str, Any] = {"feature": feature_name, "description": FEATURE_GLOSSARY[feature_name]}
        if feature_name in svc.numeric_and_binary:
            info["type"] = "numeric"
            info["range"] = svc.schema["numeric_ranges"].get(feature_name)
        elif feature_name in svc.categorical_cols:
            info["type"] = "categorical"
            info["options"] = svc.schema["categorical_options"].get(feature_name, [])
        return info
    return {"features": [{"feature": k, "description": v} for k, v in FEATURE_GLOSSARY.items()]}


def tool_get_model_metrics(services: dict[str, Any], model: str | None = None, **_: Any) -> dict[str, Any]:
    svc = _get_service(services)
    if model:
        resolved = svc.resolve_model_name(model)
        if resolved not in svc.metrics:
            return {"error": f"Unknown model: {model!r}", "available_models": svc.available_models}
        return {"model": resolved, "label": svc.model_label(resolved), "is_best": resolved == svc.best_model,
                "metrics": svc.metrics[resolved]}
    ranked = sorted(svc.available_models, key=lambda m: svc.metrics[m]["validation_rmse"])
    return {
        "best_model": svc.best_model,
        "leaderboard": [
            {"model": m, "label": svc.model_label(m), "is_best": m == svc.best_model,
             "validation_r2": svc.metrics[m]["validation_r2"], "validation_rmse": svc.metrics[m]["validation_rmse"],
             "test_r2": svc.metrics[m]["test_r2"], "test_rmse": svc.metrics[m]["test_rmse"]}
            for m in ranked
        ],
    }


def tool_predict_shelf_life(services: dict[str, Any], features: dict[str, Any] | None = None, model: str | None = None, **_: Any) -> dict[str, Any]:
    svc = _get_service(services)
    row = svc.default_row()
    row.update(features or {})
    try:
        return svc.predict_one(model or svc.best_model, row)
    except Exception as exc:  # noqa: BLE001 -- surfaced to the LLM as a tool error, not raised
        return {"error": str(exc)}


def tool_compare_treatments(
    services: dict[str, Any], shared: dict[str, Any] | None = None,
    candidates: list[dict[str, Any]] | None = None, model: str | None = None, **_: Any,
) -> dict[str, Any]:
    svc = _get_service(services)
    if not candidates:
        return {"error": "At least one candidate treatment is required (name, treatment_type, application_method, primary_ingredient_name, primary_concentration, primary_concentration_unit)."}
    try:
        built = [build_candidate_row(c) for c in candidates]
        return svc.compare_control_vs_candidates(model or svc.best_model, shared or {}, built)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def tool_explain_prediction(services: dict[str, Any], features: dict[str, Any] | None = None, model: str | None = None, top_k: int = 8, **_: Any) -> dict[str, Any]:
    svc = _get_service(services)
    row = svc.default_row()
    row.update(features or {})
    try:
        factors = svc.local_explanation(model or svc.best_model, row, top_k=top_k)
        return {"model": svc.resolve_model_name(model or svc.best_model), "factors": factors}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def tool_get_references(services: dict[str, Any], **_: Any) -> dict[str, Any]:
    return _get_service(services).dataset_references()


TOOL_IMPLS: dict[str, Callable[..., dict[str, Any]]] = {
    "get_project_overview": tool_get_project_overview,
    "get_dataset_statistics": tool_get_dataset_statistics,
    "get_feature_information": tool_get_feature_information,
    "get_model_metrics": tool_get_model_metrics,
    "predict_shelf_life": tool_predict_shelf_life,
    "compare_treatments": tool_compare_treatments,
    "explain_prediction": tool_explain_prediction,
    "get_references": tool_get_references,
}

TOOL_SPECS: list[dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "get_project_overview",
        "description": "Explains what Shelf-Life Studio is, how its training pipeline works end to end, and its current best model. Call this for any question about the project's purpose or methodology.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_dataset_statistics",
        "description": "Returns real dataset statistics: row/context counts, distributions of cheese categories, food matrices, packaging types, indicators, ingredients, and shelf-life-days summary stats. Optionally filter to one cheese_category.",
        "parameters": {"type": "object", "properties": {
            "cheese_category": {"type": "string", "enum": ["hard", "semi_hard", "soft"], "description": "Optional filter."},
        }},
    }},
    {"type": "function", "function": {
        "name": "get_feature_information",
        "description": "Explains what a dataset feature/column means, and (if applicable) its valid range or categorical options. Omit feature_name to list every feature.",
        "parameters": {"type": "object", "properties": {
            "feature_name": {"type": "string", "description": "Exact column name, e.g. 'matrix_water_activity'."},
        }},
    }},
    {"type": "function", "function": {
        "name": "get_model_metrics",
        "description": "Returns validation/test metrics (R2, RMSE, MAE) for one model, or the full leaderboard ranked by validation RMSE if no model is given. Use this to answer 'which model is best' or 'what is the accuracy of X'.",
        "parameters": {"type": "object", "properties": {
            "model": {"type": "string", "description": "One of random_forest, lightgbm, xgboost, ebm, lstm. Omit for the full leaderboard."},
        }},
    }},
    {"type": "function", "function": {
        "name": "predict_shelf_life",
        "description": "Predicts shelf_life_days for a single formulation. Any feature not given defaults to a typical (median/mode) training value. Use this for direct 'what would the shelf life be if...' questions.",
        "parameters": {"type": "object", "properties": {
            "features": {"type": "object", "description": "Partial map of feature_name -> value, e.g. {\"cheese_category\": \"soft\", \"storage_temperature_c\": 4}."},
            "model": {"type": "string", "description": "Model to use; defaults to the best model."},
        }},
    }},
    {"type": "function", "function": {
        "name": "compare_treatments",
        "description": "Compares one or more candidate treatments against an untreated control under the same shared conditions, returning predicted shelf life and % improvement for each. Use this for 'how much does ingredient X extend shelf life' questions.",
        "parameters": {"type": "object", "properties": {
            "shared": {"type": "object", "description": "Shared formulation/storage conditions applied to both control and candidates (e.g. cheese_category, food_matrix, storage_temperature_c)."},
            "candidates": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "treatment_type": {"type": "string"},
                "application_method": {"type": "string"}, "primary_ingredient_name": {"type": "string"},
                "primary_concentration": {"type": "number"}, "primary_concentration_unit": {"type": "string"},
                "primary_ingredient_family": {"type": "string"},
            }, "required": ["name", "treatment_type", "application_method", "primary_ingredient_name", "primary_concentration", "primary_concentration_unit"]}},
            "model": {"type": "string", "description": "Model to use; defaults to the best model."},
        }, "required": ["candidates"]},
    }},
    {"type": "function", "function": {
        "name": "explain_prediction",
        "description": "Explains which features drove a prediction up or down (local feature attribution) for a given formulation. Use this for 'why did the model predict X' questions.",
        "parameters": {"type": "object", "properties": {
            "features": {"type": "object", "description": "Partial map of feature_name -> value describing the formulation to explain."},
            "model": {"type": "string", "description": "Model to use; defaults to the best model."},
            "top_k": {"type": "integer", "description": "How many top factors to return (default 8)."},
        }},
    }},
    {"type": "function", "function": {
        "name": "get_references",
        "description": "Returns dataset provenance: how many rows are real vs synthetic, and the synthetic generation method/rules used. Use this for 'where does this data come from' questions.",
        "parameters": {"type": "object", "properties": {}},
    }},
]
