"""
Routes V6 predictions to the correct specialist model (by cheese_category)
and task (general_shelf_life vs safety_endpoint), and resolves the cheese
catalog / physical-form support levels the guided frontend flow needs.

Additive to the existing single-model app: SpecialistRegistry loads its own
artifacts_v6/{category}/{task}/ directories via ModelService (parameterized
for this purpose in model_service.py); nothing here is imported by the
legacy /api/predict path, and a missing specialist degrades gracefully
(never crashes the whole API), mirroring the classification_service.py /
ingredient_ranking_service.py defensive-load pattern already used in
backend/main.py.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from model_service import ModelService
from train_specialists import DATA_VERSION_CONFIG

logger = logging.getLogger("shelf_life.specialist_registry")

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "raw"

CATEGORIES = ["soft", "semi_hard", "hard"]
TASKS = ["general_shelf_life", "safety_endpoint"]


def resolve_support_level(confidence: float | None, source: str | None = None) -> dict[str, str]:
    """Bands grounded directly in the V6 data's own physical_form_confidence
    scale (verified against the actual data during planning):
      explicit_matrix_name                  -> confidence 1.0 (exact match in training)
      inferred_from_category_and_ripening    -> constant 0.75
      inferred_typical                       -> ranges 0.40-0.98
    Never fabricates a confidence score -- a missing value is always
    reported as unsupported, not defaulted to something reassuring."""
    if confidence is None:
        return {
            "level": "unsupported",
            "label": "Experimental",
            "explanation": "No training-support information is available for this combination.",
        }
    if confidence >= 1.0:
        return {
            "level": "strong",
            "label": "Strong",
            "explanation": "This exact cheese and physical form appear directly in the training data.",
        }
    if confidence >= 0.85:
        return {
            "level": "moderate",
            "label": "Moderate",
            "explanation": "This physical form is well represented for closely related products in this category.",
        }
    if confidence >= 0.6:
        return {
            "level": "limited",
            "label": "Limited",
            "explanation": "This physical form is inferred as typical for this cheese, not directly observed in training.",
        }
    return {
        "level": "experimental",
        "label": "Experimental",
        "explanation": "This combination is outside the training data's reliable support -- treat this prediction as exploratory.",
    }


def build_cheese_catalog(data_version: str = "v6") -> dict[str, list[dict[str, Any]]]:
    """base_cheese_name -> list of catalog entries, one per distinct
    cheese_category (a list, not a scalar, since e.g. 'kalari cheese'
    genuinely spans two categories in the V6 data -- that's a real
    disambiguation the user should be asked about).

    food_matrix intentionally lives on each physical-form OPTION, not on the
    entry: a handful of base names (cheddar, processed cheese) have more
    than one food_matrix value within the SAME category, one per physical
    form (e.g. cheddar/food_matrix=cheddar -> block, cheddar/food_matrix=
    "shredded cheddar" -> shredded). Keeping food_matrix at the entry level
    would force a same-category, different-form pair through the
    category-disambiguation UI with two indistinguishable "Hard"/"Hard"
    choices -- confirmed as a real bug via an end-to-end Playwright run.
    Each physical form keeps its own food_matrix so /api/v6/predict still
    gets the specific value the model was trained on."""
    csv_pattern = DATA_VERSION_CONFIG[data_version]["csv_pattern"]
    frames = []
    for category in CATEGORIES:
        csv_path = DATA_DIR / csv_pattern.format(CAT=category.upper())
        frames.append(pd.read_csv(csv_path))
    all_df = pd.concat(frames, ignore_index=True)

    catalog: dict[str, list[dict[str, Any]]] = {}
    for base_name, g in all_df.groupby("base_cheese_name"):
        entries = []
        for category, gg in g.groupby("cheese_category"):
            forms = []
            for (food_matrix, form), ggg in gg.groupby(["food_matrix", "physical_form"]):
                best_row = ggg.loc[ggg["physical_form_confidence"].idxmax()]
                support = resolve_support_level(float(best_row["physical_form_confidence"]), str(best_row["physical_form_source"]))
                forms.append({
                    "physicalForm": str(form),
                    "foodMatrix": str(food_matrix),
                    "source": str(best_row["physical_form_source"]),
                    "confidence": float(best_row["physical_form_confidence"]),
                    "support": support,
                })
            forms.sort(key=lambda f: -f["confidence"])
            entries.append({
                "cheeseCategory": str(category),
                "physicalForms": forms,
            })
        catalog[str(base_name)] = entries
    return catalog


class SpecialistRegistry:
    """{soft: {general_shelf_life: ModelService, safety_endpoint: ModelService}, semi_hard: {...}, hard: {...}}"""

    def __init__(self, data_version: str = "v6") -> None:
        self.data_version = data_version
        version_cfg = DATA_VERSION_CONFIG[data_version]
        artifacts_dir_root = ROOT / version_cfg["artifacts_dir"]
        self.services: dict[str, dict[str, ModelService | None]] = {c: {} for c in CATEGORIES}
        for category in CATEGORIES:
            csv_path = DATA_DIR / version_cfg["csv_pattern"].format(CAT=category.upper())
            for task in TASKS:
                artifacts_dir = artifacts_dir_root / category / task
                try:
                    svc = ModelService(artifacts_dir=artifacts_dir, data_path=csv_path, data_sheet=None)
                    # ModelService loads the whole category CSV as full_df by
                    # design (for matrix/ingredient lookups); scope it down to
                    # just this task's rows so dataset_statistics()/etc. stay
                    # specialist-scoped rather than mixing tasks.
                    svc.full_df = svc.full_df[svc.full_df["model_task"] == task].reset_index(drop=True)
                    self.services[category][task] = svc
                    logger.info("Loaded specialist %s/%s (n_train=%s, best=%s)",
                                category, task, svc.manifest.get("n_train"), svc.best_model)
                except FileNotFoundError as exc:
                    self.services[category][task] = None
                    logger.warning("Specialist %s/%s not available: %s", category, task, exc)

        self.cheese_catalog = build_cheese_catalog(data_version)
        self._assert_specialist_isolation()

    def _assert_specialist_isolation(self) -> None:
        """Hardening check, not a bug fix -- each ModelService instance
        already owns its own model/preprocessor/schema objects with no
        shared mutable state, verified during the audit. This makes that
        guarantee explicit and durable: if a future refactor ever
        accidentally shares a preprocessor or schema object between two
        specialists, this fails loudly at startup instead of silently
        mixing feature spaces at prediction time."""
        seen: dict[int, str] = {}
        for category, tasks in self.services.items():
            for task, svc in tasks.items():
                if svc is None:
                    continue
                for label, obj in (("tree_pre", svc.tree_pre), ("ebm_pre", svc.ebm_pre), ("schema", svc.schema)):
                    key = id(obj)
                    owner = f"{category}/{task}:{label}"
                    if key in seen:
                        raise RuntimeError(
                            f"Specialist isolation violated: {owner} shares an object with {seen[key]} "
                            f"-- a model would be served with another specialist's preprocessing/schema."
                        )
                    seen[key] = owner

    def indicator_task_map(self, cheese_category: str) -> dict[str, str]:
        """The single authoritative indicator_type -> model_task lookup for
        a category, built once from each specialist's own trained schema
        (categorical_options.indicator_type) -- not re-derived anywhere
        else. The frontend calls /api/v6/routing (which wraps this) instead
        of independently reconstructing this membership itself."""
        mapping: dict[str, str] = {}
        for task in TASKS:
            svc = self.services.get(cheese_category, {}).get(task)
            if svc is None:
                continue
            for indicator in svc.schema["categorical_options"].get("indicator_type", []):
                mapping[indicator] = task
        return mapping

    def resolve(self, cheese_category: str, model_task: str) -> tuple[ModelService | None, dict[str, Any]]:
        """Returns (service_to_use, routing_meta). routing_meta always
        carries reduced_support (bool) + reason (str | None). A missing
        specialist returns (None, ...) -- there is NO fallback to a
        different task or category. A caller that gets None back must not
        attempt a prediction; see backend/main.py's /api/v6/predict, which
        hard-fails with an explicit error rather than silently substituting
        a different specialist (this was previously a safety->general
        fallback here; removed per explicit audit requirement -- a safety
        prediction must never be silently served by the general model)."""
        if cheese_category not in CATEGORIES:
            return None, {"level": "unavailable", "reduced_support": True, "reason": f"Unknown cheese_category: {cheese_category!r}"}
        if model_task not in TASKS:
            return None, {"level": "unavailable", "reduced_support": True, "reason": f"Unknown model_task: {model_task!r}"}

        svc = self.services[cheese_category].get(model_task)
        if svc is None:
            return None, {
                "level": "unavailable", "reduced_support": True,
                "reason": f"No specialist model is available for {cheese_category}/{model_task}. "
                          f"This prediction cannot be served -- there is no fallback to a different specialist.",
            }

        thin = bool(svc.manifest.get("thin_split"))
        if thin:
            return svc, {
                "level": "thin_sample", "reduced_support": True,
                "reason": f"This specialist was trained on a limited sample (n_train={svc.manifest.get('n_train')}); "
                          f"treat this prediction with extra caution.",
            }
        return svc, {"level": "ok", "reduced_support": False, "reason": None}

    def assess_prediction_support(self, cheese_category: str, model_task: str, row: dict[str, Any]) -> dict[str, Any]:
        """The single combined support assessment used by BOTH
        /api/v6/predict and any validation/evaluation script (audit item
        #10 -- one code path, not a separate approximate reimplementation
        for validation). Combines: specialist availability (resolve()),
        physical_form presence (must be explicit, never silently defaulted
        -- audit item #4) and support level (resolve_support_level, using
        the row's actual physical_form_confidence/source if supplied by the
        caller, or looked up from the catalog otherwise), and the
        model-level categorical/numeric assessment (ModelService.assess_support)."""
        svc, routing_meta = self.resolve(cheese_category, model_task)
        if svc is None:
            return {
                "level": "unavailable", "can_predict": False,
                "reason": routing_meta["reason"], "routing": routing_meta,
                "physical_form": None, "model": None,
            }

        physical_form = row.get("physical_form")
        if not physical_form:
            return {
                "level": "missing_physical_form", "can_predict": False,
                "reason": "physical_form is required and must be explicitly selected -- it is never silently "
                          "defaulted to a guessed 'typical' form for a live prediction.",
                "routing": routing_meta, "physical_form": None, "model": None,
            }

        pf_support = self._physical_form_support(cheese_category, row.get("food_matrix"), physical_form)
        model_assessment = svc.assess_support(row)

        # Precedence: unavailable/missing-form already returned above.
        # Otherwise: unsupported categorical > weak physical-form > numerical
        # extrapolation > supported. Each is reported explicitly, not merged
        # away, but the UI needs one headline level to key its treatment on.
        if model_assessment["level"] == "unsupported_categorical":
            level = "unsupported_categorical"
        elif pf_support and pf_support["level"] in ("limited", "experimental", "unsupported"):
            level = "weak_physical_form"
        elif model_assessment["level"] == "extrapolation":
            level = "extrapolation"
        elif routing_meta["level"] == "thin_sample":
            level = "thin_sample"
        else:
            level = "supported"

        return {
            "level": level, "can_predict": True,
            "reason": None, "routing": routing_meta,
            "physical_form": pf_support, "model": model_assessment,
        }

    def _physical_form_support(self, cheese_category: str, food_matrix: Any, physical_form: Any) -> dict[str, Any] | None:
        for base_name, entries in self.cheese_catalog.items():
            for entry in entries:
                if entry["cheeseCategory"] != cheese_category:
                    continue
                for form in entry["physicalForms"]:
                    if form["foodMatrix"] == food_matrix and form["physicalForm"] == physical_form:
                        return form["support"]
        # Genuinely unknown combination -- never fabricate a confidence.
        return resolve_support_level(None)

    def cheese_entries(self, base_cheese_name: str) -> list[dict[str, Any]]:
        return self.cheese_catalog.get(base_cheese_name, [])
