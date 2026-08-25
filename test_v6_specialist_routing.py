#!/usr/bin/env python
"""
Tests for the hardened V6 prediction pipeline (specialist_registry.py,
model_service.py). Imports the exact same objects backend/main.py uses --
no separate/approximate reimplementation of routing, preprocessing, or unit
conversion for testing (audit item #10).

Usage: python -m pytest test_v6_specialist_routing.py -v
"""
from __future__ import annotations

import pytest

from concentration_units import to_canonical, UnrecognizedConcentrationUnit
from specialist_registry import SpecialistRegistry, CATEGORIES, TASKS

BASE_ROW = {
    "food_matrix": "cheddar", "physical_form": "block",
    "matrix_ph": 5.2, "matrix_water_activity": 0.94, "matrix_moisture_pct": 37.0,
    "matrix_fat_pct": 33.0, "matrix_protein_pct": 25.0, "matrix_salt_pct": 1.7,
    "matrix_ripening_days": 60, "pasteurization_applied": 1, "storage_temperature_c": 4.0,
    "packaging_type": "vacuum", "headspace_oxygen_pct": 0.5, "headspace_co2_pct": 0.0, "headspace_n2_pct": 0.0,
    "indicator_group": "microbiological", "indicator_type": "listeria_monocytogenes",
    "indicator_threshold": 2.0, "indicator_unit": "log CFU/g", "initial_indicator_value": 0.2,
    "is_control": 1, "treatment_type": "none", "application_method": "none", "ingredient_count": 0,
    "primary_ingredient_name": "none", "primary_ingredient_family": "none",
    "canonical_concentration_value": 0.0, "canonical_concentration_unit": "none",
}


@pytest.fixture(scope="module")
def registry() -> SpecialistRegistry:
    return SpecialistRegistry()


# ── 1. All six specialist routes resolve ────────────────────────────────────

@pytest.mark.parametrize("category", CATEGORIES)
@pytest.mark.parametrize("task", TASKS)
def test_all_six_specialists_resolve(registry: SpecialistRegistry, category: str, task: str) -> None:
    svc, meta = registry.resolve(category, task)
    assert svc is not None, f"{category}/{task} did not resolve"
    assert meta["level"] in ("ok", "thin_sample")


# ── 2. Unseen pathogen ───────────────────────────────────────────────────────

def test_unseen_pathogen_flagged_not_blocked(registry: SpecialistRegistry) -> None:
    row = {**BASE_ROW, "indicator_type": "brand_new_pathogen_xyz"}
    support = registry.assess_prediction_support("hard", "safety_endpoint", row)
    assert support["can_predict"] is True
    assert support["level"] == "unsupported_categorical"
    assert any(u["feature"] == "indicator_type" for u in support["model"]["unseen_categoricals"])


# ── 3. Unseen ingredient ─────────────────────────────────────────────────────

def test_unseen_ingredient_flagged(registry: SpecialistRegistry) -> None:
    row = {**BASE_ROW, "primary_ingredient_name": "unobtainium_extract", "ingredient_count": 1}
    support = registry.assess_prediction_support("hard", "general_shelf_life", row)
    assert support["level"] == "unsupported_categorical"
    assert any(u["feature"] == "primary_ingredient_name" for u in support["model"]["unseen_categoricals"])


# ── 4. Unseen packaging ───────────────────────────────────────────────────────

def test_unseen_packaging_flagged(registry: SpecialistRegistry) -> None:
    row = {**BASE_ROW, "packaging_type": "hermetically_sealed_titanium"}
    support = registry.assess_prediction_support("hard", "general_shelf_life", row)
    assert support["level"] == "unsupported_categorical"
    assert any(u["feature"] == "packaging_type" for u in support["model"]["unseen_categoricals"])


# ── 5. Invalid concentration unit ────────────────────────────────────────────

def test_invalid_concentration_unit_raises() -> None:
    with pytest.raises(UnrecognizedConcentrationUnit):
        to_canonical(10.0, "furlongs_per_fortnight")


def test_valid_concentration_unit_converts() -> None:
    value, unit = to_canonical(10.0, "ppm")
    assert unit == "mg/kg"
    assert value == pytest.approx(10.0)


# ── 6. Out-of-range numeric values (conditional, not pooled) ────────────────

def test_numeric_extrapolation_uses_conditional_range(registry: SpecialistRegistry) -> None:
    row = {**BASE_ROW, "indicator_threshold": 500.0}
    svc, _ = registry.resolve("hard", "safety_endpoint")
    assessment = svc.assess_support(row)
    assert assessment["level"] == "extrapolation"
    hit = next(e for e in assessment["extrapolations"] if e["feature"] == "indicator_threshold")
    # Must be conditioned on (indicator_type, indicator_unit), not the flat
    # pooled range -- the whole point of the fix.
    assert hit["conditioned_on"] is not None
    assert hit["conditioned_on"]["indicator_type"] == "listeria_monocytogenes"


def test_in_range_numeric_is_supported(registry: SpecialistRegistry) -> None:
    svc, _ = registry.resolve("hard", "safety_endpoint")
    assessment = svc.assess_support(BASE_ROW)
    assert assessment["level"] == "supported"
    assert assessment["extrapolations"] == []


# ── 7. Missing specialist -- no fallback ─────────────────────────────────────

def test_missing_specialist_no_fallback(registry: SpecialistRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate a missing safety specialist and confirm resolve() does NOT
    # silently substitute the general model -- the exact bug this hardening
    # pass removed.
    real_svc = registry.services["hard"]["safety_endpoint"]
    monkeypatch.setitem(registry.services["hard"], "safety_endpoint", None)
    try:
        svc, meta = registry.resolve("hard", "safety_endpoint")
        assert svc is None
        assert meta["level"] == "unavailable"
        assert "no fallback" in meta["reason"].lower() or "cannot be served" in meta["reason"].lower()

        support = registry.assess_prediction_support("hard", "safety_endpoint", BASE_ROW)
        assert support["can_predict"] is False
        assert support["level"] == "unavailable"
    finally:
        registry.services["hard"]["safety_endpoint"] = real_svc


def test_unknown_category_no_fallback(registry: SpecialistRegistry) -> None:
    svc, meta = registry.resolve("nonexistent_category", "general_shelf_life")
    assert svc is None
    assert meta["level"] == "unavailable"


# ── 8. Physical-form support levels ──────────────────────────────────────────

def test_physical_form_strong_support_is_explicit(registry: SpecialistRegistry) -> None:
    # shredded cheddar is explicit_matrix_name / confidence 1.0 -- verified
    # during the original V6 build.
    support = registry._physical_form_support("hard", "shredded cheddar", "shredded")
    assert support["level"] == "strong"


def test_physical_form_inferred_is_not_strong(registry: SpecialistRegistry) -> None:
    # plain cheddar/block is inferred_typical -- must never be reported as
    # if it were directly observed.
    support = registry._physical_form_support("hard", "cheddar", "block")
    assert support["level"] != "strong"


def test_missing_physical_form_hard_blocks(registry: SpecialistRegistry) -> None:
    row = dict(BASE_ROW)
    del row["physical_form"]
    support = registry.assess_prediction_support("hard", "safety_endpoint", row)
    assert support["can_predict"] is False
    assert support["level"] == "missing_physical_form"


def test_unknown_physical_form_combo_never_fabricates_confidence(registry: SpecialistRegistry) -> None:
    support = registry._physical_form_support("hard", "cheddar", "a_form_that_does_not_exist")
    assert support["level"] == "unsupported"


# ── 9. Preprocessing consistency between assessment and inference ──────────

def test_assess_support_and_predict_use_same_schema(registry: SpecialistRegistry) -> None:
    svc, _ = registry.resolve("hard", "safety_endpoint")
    assessment = svc.assess_support(BASE_ROW)
    result = svc.predict_one(svc.best_model, BASE_ROW)
    # predict_one's attached support must be identical in shape/content to a
    # direct assess_support call on the same row -- one code path, not two.
    assert result["support"]["level"] == assessment["level"]
    assert result["support"]["unseen_categoricals"] == assessment["unseen_categoricals"]


def test_specialist_isolation(registry: SpecialistRegistry) -> None:
    soft_general = registry.services["soft"]["general_shelf_life"]
    hard_safety = registry.services["hard"]["safety_endpoint"]
    assert soft_general.tree_pre is not hard_safety.tree_pre
    assert soft_general.schema is not hard_safety.schema
    assert soft_general.feature_cols != hard_safety.feature_cols or soft_general is not hard_safety


# ── 10. Safety/general endpoint routing (single source of truth) ───────────

def test_indicator_task_map_matches_training_data(registry: SpecialistRegistry) -> None:
    mapping = registry.indicator_task_map("hard")
    assert mapping["listeria_monocytogenes"] == "safety_endpoint"
    assert mapping.get("yeasts_molds", mapping.get("sensory_acceptability")) == "general_shelf_life"


def test_indicator_task_map_has_no_ambiguity(registry: SpecialistRegistry) -> None:
    for category in CATEGORIES:
        general_svc = registry.services[category]["general_shelf_life"]
        safety_svc = registry.services[category]["safety_endpoint"]
        if general_svc is None or safety_svc is None:
            continue
        general_indicators = set(general_svc.schema["categorical_options"].get("indicator_type", []))
        safety_indicators = set(safety_svc.schema["categorical_options"].get("indicator_type", []))
        overlap = general_indicators & safety_indicators
        assert not overlap, f"{category}: indicator_type values in both tasks: {overlap}"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
