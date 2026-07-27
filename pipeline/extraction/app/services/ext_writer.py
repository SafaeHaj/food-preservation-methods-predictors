"""Persist an LLM extraction result into the `ext_*` tables.

There were two copies of this logic -- one in `extraction_workspace._run_llm_validation`,
one in `food_extraction._run_food_extraction` -- and the first even carried the comment
"same logic as food_extraction.py". They had already drifted: only one recorded evidence
anchors, and their duplicate-guard behaviour differed. This is the single copy; the
evidence anchoring the workspace path lacked is available to both through the optional
`evidence_sink`.

The writer performs no commits. Its caller wraps it in `unit_of_work`, so an LLM result
lands whole or not at all -- a partially-persisted extraction is indistinguishable from a
complete one downstream, and the previous per-row `flush`+`commit` mix could produce one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from shared.db.models import (
    ExtExperiment, ExtExperimentIngredient, ExtIndicator, ExtIngredient, ExtMeasurement,
)

logger = logging.getLogger(__name__)

#: Called as sink(entity_type, entity_key, field_name, evidence_dict) when the caller wants
#: evidence anchors written. The workspace path passes None (it has no page bboxes to crop).
EvidenceSink = Callable[[str, dict, Optional[str], dict], None]


@dataclass
class WriteResult:
    experiments: int = 0
    measurements: int = 0
    skipped: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"experiments": self.experiments, "measurements": self.measurements}


def _coerce_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_or_create_ingredient(
    db: Session, project_id: int, name: str, functional_class: str, source: str
) -> ExtIngredient:
    ingredient = (
        db.query(ExtIngredient)
        .filter(ExtIngredient.project_id == project_id, ExtIngredient.ingredient_name == name)
        .first()
    )
    if ingredient:
        return ingredient
    ingredient = ExtIngredient(
        project_id=project_id,
        ingredient_name=name,
        functional_class=functional_class or "unknown",
        source=source or "",
    )
    db.add(ingredient)
    db.flush()
    return ingredient


def _get_or_create_indicator(
    db: Session, project_id: int, indicator_type: str, indicator_unit: str,
    threshold: Optional[float],
) -> ExtIndicator:
    indicator = (
        db.query(ExtIndicator)
        .filter(
            ExtIndicator.project_id == project_id,
            ExtIndicator.indicator_type == indicator_type,
            ExtIndicator.indicator_unit == indicator_unit,
        )
        .first()
    )
    if not indicator:
        indicator = ExtIndicator(
            project_id=project_id,
            indicator_type=indicator_type,
            indicator_unit=indicator_unit,
            indicator_threshold=threshold,
        )
        db.add(indicator)
        db.flush()
    elif threshold is not None and indicator.indicator_threshold is None:
        # A later paper may report the regulatory limit the first one omitted.
        indicator.indicator_threshold = threshold
    return indicator


def _write_ingredients(
    db: Session, project_id: int, experiment: ExtExperiment,
    ingredient_dicts: list[dict], evidence_sink: Optional[EvidenceSink],
) -> None:
    for ingredient_dict in ingredient_dicts:
        name = ingredient_dict.get("ingredient_name") or ""
        concentration = _coerce_float(ingredient_dict.get("concentration"))
        if not name or concentration is None:
            continue

        ingredient = _get_or_create_ingredient(
            db, project_id, name,
            ingredient_dict.get("functional_class", "unknown"),
            ingredient_dict.get("source", ""),
        )

        link_exists = (
            db.query(ExtExperimentIngredient)
            .filter(
                ExtExperimentIngredient.experiment_id == experiment.id,
                ExtExperimentIngredient.ingredient_id == ingredient.id,
            )
            .first()
        )
        if not link_exists:
            db.add(
                ExtExperimentIngredient(
                    experiment_id=experiment.id,
                    ingredient_id=ingredient.id,
                    concentration=concentration,
                    concentration_unit=ingredient_dict.get("concentration_unit") or "",
                )
            )
            db.flush()

        if evidence_sink:
            for evidence in ingredient_dict.get("evidence", []):
                evidence_sink(
                    "ingredient_link",
                    {"experiment_id": experiment.id, "ingredient_id": ingredient.id},
                    None,
                    evidence,
                )


def _write_measurements(
    db: Session, project_id: int, experiment: ExtExperiment,
    measurement_dicts: list[dict], evidence_sink: Optional[EvidenceSink],
) -> int:
    written = 0
    for measurement_dict in measurement_dicts:
        day = _coerce_int(measurement_dict.get("day"))
        value = _coerce_float(measurement_dict.get("indicator_value"))
        indicator_type = measurement_dict.get("indicator_type") or ""
        if day is None or value is None or not indicator_type:
            continue

        indicator = _get_or_create_indicator(
            db, project_id, indicator_type,
            measurement_dict.get("indicator_unit") or "",
            _coerce_float(measurement_dict.get("indicator_threshold")),
        )

        # (experiment, day, indicator) is the composite primary key; a re-run of the same
        # paper must not raise on the duplicate.
        exists = (
            db.query(ExtMeasurement)
            .filter(
                ExtMeasurement.experiment_id == experiment.id,
                ExtMeasurement.day == day,
                ExtMeasurement.indicator_id == indicator.id,
            )
            .first()
        )
        if exists:
            continue

        db.add(
            ExtMeasurement(
                experiment_id=experiment.id,
                day=day,
                indicator_id=indicator.id,
                indicator_value=value,
                value_is_approximate=bool(measurement_dict.get("value_is_approximate", False)),
            )
        )
        db.flush()
        written += 1

        if evidence_sink:
            for evidence in measurement_dict.get("evidence", []):
                evidence_sink(
                    "measurement",
                    {"experiment_id": experiment.id, "day": day, "indicator_id": indicator.id},
                    "indicator_value",
                    evidence,
                )
    return written


def write_experiments(
    db: Session,
    *,
    project_id: int,
    paper_id: int,
    job_id: int,
    experiments: list[dict],
    evidence_sink: Optional[EvidenceSink] = None,
) -> WriteResult:
    """Persist the LLM's experiment list. Returns what was written."""
    result = WriteResult()

    for experiment_dict in experiments:
        meat_matrix = (experiment_dict.get("meat_matrix") or "").strip()
        treatment = (experiment_dict.get("treatment") or "").strip()
        if not meat_matrix or not treatment:
            # Both are NOT NULL and are the natural key of the row; an experiment missing
            # either is unusable rather than partially useful.
            result.skipped.append(
                f"experiment missing {'meat_matrix' if not meat_matrix else 'treatment'}"
            )
            continue

        experiment = ExtExperiment(
            project_id=project_id,
            paper_id=paper_id,
            job_id=job_id,
            meat_matrix=meat_matrix,
            treatment=treatment,
        )
        db.add(experiment)
        db.flush()
        result.experiments += 1

        if evidence_sink:
            for evidence in experiment_dict.get("experiment_evidence", []):
                evidence_sink("experiment", {"experiment_id": experiment.id}, None, evidence)

        _write_ingredients(
            db, project_id, experiment, experiment_dict.get("ingredients", []), evidence_sink
        )
        result.measurements += _write_measurements(
            db, project_id, experiment, experiment_dict.get("measurements", []), evidence_sink
        )

    if result.skipped:
        logger.info("Paper %s: skipped %d incomplete experiments", paper_id, len(result.skipped))
    return result
