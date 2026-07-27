"""
Normalization service.

Applies NormalizationMappings to Experiment + TreatmentArm + Observation fields.
Also handles unit conversion for common scientific units.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ── Unit conversion tables ────────────────────────────────────────────────

_TIME_TO_DAYS: dict[str, float] = {
    "day": 1.0, "days": 1.0, "d": 1.0,
    "hour": 1/24, "hours": 1/24, "h": 1/24, "hr": 1/24, "hrs": 1/24,
    "week": 7.0, "weeks": 7.0, "w": 7.0, "wk": 7.0, "wks": 7.0,
    "month": 30.0, "months": 30.0, "mo": 30.0,
    "minute": 1/1440, "minutes": 1/1440, "min": 1/1440,
}

_TEMP_CONVERSIONS: dict[str, str] = {
    "celsius": "C", "°c": "C", "c": "C",
    "fahrenheit": "F", "°f": "F", "f": "F",
    "kelvin": "K", "k": "K",
}

_CONCENTRATION_TO_CANONICAL: dict[str, str] = {
    "%": "%", "percent": "%",
    "g/l": "g/L", "g l-1": "g/L", "g·l-1": "g/L",
    "mg/l": "mg/L", "mg l-1": "mg/L",
    "µg/l": "µg/L", "ug/l": "µg/L",
    "ppm": "ppm", "ppb": "ppb",
    "m": "M", "mm": "mM", "µm": "µM", "um": "µM",
    "v/v": "v/v", "%v/v": "v/v", "% v/v": "v/v",
    "w/v": "w/v", "%w/v": "w/v", "% w/v": "w/v",
    "iu/ml": "IU/mL", "iu ml-1": "IU/mL",
}

_LOG_CFU_UNITS = {"log cfu/g", "log cfu/ml", "log cfu g-1", "log cfu ml-1",
                  "log10 cfu/g", "log10 cfu/ml", "log(cfu/g)", "cfu/g", "cfu/ml",
                  "cfu g-1", "cfu ml-1"}


def normalize_time_to_days(value: float, unit: str) -> float | None:
    factor = _TIME_TO_DAYS.get(unit.lower().strip())
    return round(value * factor, 6) if factor is not None else None


def normalize_temperature(value: float, unit: str) -> float | None:
    """Convert to Celsius."""
    u = unit.lower().strip()
    if u in ("c", "celsius", "°c"):
        return value
    if u in ("f", "fahrenheit", "°f"):
        return round((value - 32) * 5 / 9, 4)
    if u in ("k", "kelvin"):
        return round(value - 273.15, 4)
    return None


def normalize_unit_label(unit: str) -> str:
    return _CONCENTRATION_TO_CANONICAL.get(unit.lower().strip(), unit)


# ── Main normalization logic ───────────────────────────────────────────────

def run_normalization(project_id: int, db: "Session") -> dict:
    """
    Apply all normalization mappings for a project.
    Returns counts of records updated.
    """
    from shared.db.models import (
        NormalizationMapping, Experiment, TreatmentArm, Observation
    )

    mappings = (db.query(NormalizationMapping)
                  .filter(
                      (NormalizationMapping.project_id == project_id) |
                      (NormalizationMapping.project_id == None)
                  ).all())

    mapping_index: dict[tuple[str, str], str] = {
        (m.mapping_type, m.original_term.lower()): m.canonical_term
        for m in mappings
    }

    def lookup(mtype: str, original: str | None) -> str | None:
        if not original:
            return None
        return mapping_index.get((mtype, original.lower()))

    counts = {"experiments": 0, "treatment_arms": 0, "observations": 0}

    # ── Experiments ───────────────────────────────────────────────────────
    experiments = (db.query(Experiment)
                     .join(Experiment.study)
                     .filter_by(project_id=project_id)
                     .all())
    for exp in experiments:
        changed = False
        if exp.product_name_original:
            canonical = lookup("cheese_type", exp.product_name_original)
            if canonical and canonical != exp.product_name_normalized:
                exp.product_name_normalized = canonical
                changed = True
        if exp.atmosphere_type:
            canonical = lookup("packaging", exp.atmosphere_type)
            if canonical and canonical != exp.atmosphere_type:
                exp.atmosphere_type = canonical
                changed = True
        # Time normalization
        if exp.storage_duration_value and exp.storage_duration_unit_original:
            days = normalize_time_to_days(
                exp.storage_duration_value, exp.storage_duration_unit_original
            )
            if days is not None and exp.storage_duration_days != days:
                exp.storage_duration_days = days
                changed = True
        # Temperature normalization
        if exp.storage_temperature_value and exp.storage_temperature_unit_original:
            c = normalize_temperature(
                exp.storage_temperature_value, exp.storage_temperature_unit_original
            )
            if c is not None and exp.storage_temperature_c != c:
                exp.storage_temperature_c = c
                changed = True
        if changed:
            counts["experiments"] += 1

    # ── Treatment Arms ────────────────────────────────────────────────────
    arms = (db.query(TreatmentArm)
              .join(TreatmentArm.experiment)
              .join(Experiment.study)
              .filter_by(project_id=project_id)
              .all())
    for arm in arms:
        changed = False
        if arm.ingredient_name_original:
            canonical = lookup("ingredient", arm.ingredient_name_original)
            if canonical and canonical != arm.ingredient_name_normalized:
                arm.ingredient_name_normalized = canonical
                changed = True
        if arm.application_method:
            canonical = lookup("application_method", arm.application_method)
            if canonical and canonical != arm.application_method:
                arm.application_method = canonical
                changed = True
        if arm.concentration_value_original and arm.concentration_unit_original:
            canonical_unit = normalize_unit_label(arm.concentration_unit_original)
            if canonical_unit != arm.concentration_unit_normalized:
                arm.concentration_unit_normalized = canonical_unit
                arm.concentration_value_normalized = arm.concentration_value_original
                changed = True
        if changed:
            counts["treatment_arms"] += 1

    # ── Observations ──────────────────────────────────────────────────────
    observations = (db.query(Observation)
                      .join(Observation.treatment_arm)
                      .join(TreatmentArm.experiment)
                      .join(Experiment.study)
                      .filter_by(project_id=project_id)
                      .all())
    for obs in observations:
        changed = False
        # Time normalization
        if obs.time_value_original is not None and obs.time_unit_original:
            days = normalize_time_to_days(obs.time_value_original, obs.time_unit_original)
            if days is not None and obs.time_days != days:
                obs.time_days = days
                changed = True
        # Unit normalization
        if obs.unit_original:
            canonical_unit = normalize_unit_label(obs.unit_original)
            if canonical_unit != obs.unit_normalized:
                obs.unit_normalized = canonical_unit
                obs.numeric_value_normalized = obs.numeric_value_original
                changed = True
        # Measurement type normalization
        if obs.measurement_type:
            canonical = lookup("measurement_type", obs.measurement_type)
            if canonical and canonical != obs.measurement_type:
                obs.measurement_type = canonical
                changed = True
        if changed:
            counts["observations"] += 1

    db.commit()

    # Update applied counts for used mappings
    for m in mappings:
        db.refresh(m)

    return counts
