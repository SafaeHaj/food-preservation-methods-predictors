"""Persist a validated `GoldBundle` into the scientific schema.

It takes records, not dictionaries. That is the difference from the previous writer, which
coerced whatever the model returned — `_coerce_float`, `_coerce_int`, a `functional_class`
defaulting to "unknown" — and so could not tell a missing field from an unparseable one.
Everything here has already been validated against `shared.schemas.science`, so the writer's
job is resolution and identity, not repair.

Performs no commits. Its caller wraps it in `unit_of_work`, so a paper's experiments, its
ingredient links, its measurements and their evidence commit together: the scientific
database can never show half of a paper.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from shared.db.models import (
    Experiment, ExperimentIngredient, Indicator, Ingredient, MatrixProfile, Measurement,
    TreatmentProfile,
)
from shared.schemas.science import ExperimentRecord, GoldBundle

logger = logging.getLogger(__name__)

#: Called as sink(entity_type, entity_key, field_name, span) when the caller wants evidence
#: anchors written. Kept as a parameter so the writer has no opinion about crops or files.
EvidenceSink = Callable[[str, dict, Optional[str], Any], None]


@dataclass
class WriteResult:
    experiments: int = 0
    measurements: int = 0
    ingredients: int = 0
    evidence: int = 0
    new_terms: list = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "experiments": self.experiments,
            "measurements": self.measurements,
            "ingredients": self.ingredients,
            "evidence": self.evidence,
            "new_terms": self.new_terms,
        }


#: Stands in for a null inside `treatment_key`. Two arms whose temperature is unstated are
#: the same treatment, but SQL compares their NULLs as distinct, so the key spells them.
_UNSTATED = "-"

#: The measured composition fields, identical in name on the record and both tables.
_COMPOSITION = (
    "ph", "water_activity", "moisture_percent", "fat_percent", "protein_percent",
    "salt_percent", "initial_tvc_log_cfu_g",
)


def _get_or_create_ingredient(db: Session, record) -> tuple[Ingredient, bool]:
    """Global, not per project: the substance is the same one in every project, and the
    molecular features hanging off it describe it rather than any team's use of it."""
    ingredient = (
        db.query(Ingredient)
        .filter(Ingredient.ingredient_name == record.ingredient_name)
        .first()
    )
    if ingredient:
        return ingredient, False
    ingredient = Ingredient(
        ingredient_name=record.ingredient_name,
        functional_class=record.functional_class,
        source_category=record.source_category,
    )
    db.add(ingredient)
    db.flush()
    return ingredient, True


def _get_or_create_indicator(db: Session, record) -> tuple[Indicator, bool]:
    indicator = (
        db.query(Indicator)
        .filter(Indicator.indicator_name == record.indicator_name,
                Indicator.indicator_unit == record.indicator_unit)
        .first()
    )
    if not indicator:
        indicator = Indicator(
            indicator_name=record.indicator_name,
            indicator_type=record.indicator_type,
            indicator_unit=record.indicator_unit,
            indicator_threshold=record.indicator_threshold,
        )
        db.add(indicator)
        db.flush()
        return indicator, True
    if record.indicator_threshold is not None and indicator.indicator_threshold is None:
        # A later paper may report the regulatory limit the first one omitted.
        indicator.indicator_threshold = record.indicator_threshold
    return indicator, False


def _get_or_create_matrix(db: Session, record: ExperimentRecord) -> MatrixProfile:
    """The named food this arm used, corpus-wide.

    Fill-never-overwrite: a paper that measured a pH fills the profile's null, but a second
    paper measuring a different pH does not overwrite the first. The profile is the
    *reference* value and the per-paper number belongs on the experiment, where the
    provenance stays readable. Without this rule the reference column would drift to
    whichever paper happened to be ingested last.
    """
    profile = (
        db.query(MatrixProfile)
        .filter(MatrixProfile.matrix_name == record.matrix_name)
        .first()
    )
    if profile is None:
        profile = MatrixProfile(matrix_name=record.matrix_name, source="manual")
        db.add(profile)
        db.flush()
    for name in _COMPOSITION:
        if getattr(profile, name) is None and getattr(record.composition, name) is not None:
            setattr(profile, name, getattr(record.composition, name))
    return profile


def _treatment_key(record: ExperimentRecord) -> str:
    parts = (record.treatment_type, record.thermal_temperature_c, record.thermal_duration_min)
    return "|".join(_UNSTATED if part is None else str(part) for part in parts)


def _get_or_create_treatment(db: Session, record: ExperimentRecord) -> Optional[TreatmentProfile]:
    """The distinct physical treatment, deduplicated corpus-wide. None when unclassified —
    an arm that went through no treatment must not point at a row saying it did."""
    if record.treatment_type is None:
        return None
    key = _treatment_key(record)
    profile = (
        db.query(TreatmentProfile)
        .filter(TreatmentProfile.treatment_key == key)
        .first()
    )
    if profile is None:
        profile = TreatmentProfile(
            treatment_type=record.treatment_type,
            thermal_temperature_c=record.thermal_temperature_c,
            thermal_duration_min=record.thermal_duration_min,
            treatment_key=key,
        )
        db.add(profile)
        db.flush()
    return profile


def _get_or_create_experiment(
    db: Session, *, project_id: int, paper_id: int, job_id: int, record: ExperimentRecord
) -> Experiment:
    """Find this paper's arm or create it, keyed on (matrix, treatment, arm_key).

    Re-extracting a paper must update its arms rather than duplicate them. `arm_key` is
    load-bearing and not decoration: every rung of a dose ladder shares a matrix and a
    treatment, so a key of the two profile ids alone silently folds eleven arms into one
    and the measurements of all of them land on whichever won. The conditions an arm was
    run under -- mass, storage, packaging -- stay out of the key, because a corrected
    number describes the same arm.
    """
    matrix = _get_or_create_matrix(db, record)
    treatment = _get_or_create_treatment(db, record)
    treatment_id = treatment.id if treatment else None

    experiment = (
        db.query(Experiment)
        .filter(Experiment.project_id == project_id,
                Experiment.paper_id == paper_id,
                Experiment.matrix_id == matrix.id,
                Experiment.arm_key == record.arm_key,
                Experiment.treatment_id.is_(None) if treatment_id is None
                else Experiment.treatment_id == treatment_id)
        .first()
    )
    if experiment is None:
        experiment = Experiment(
            project_id=project_id, paper_id=paper_id, job_id=job_id,
            matrix_id=matrix.id, treatment_id=treatment_id, arm_key=record.arm_key,
        )
        db.add(experiment)

    experiment.job_id = job_id
    experiment.treatment_description = record.treatment_description
    experiment.sample_weight_g = record.sample_weight_g
    experiment.storage_temperature_c = record.storage_temperature_c
    experiment.map_o2_percent = record.map_o2_percent
    experiment.map_co2_percent = record.map_co2_percent
    experiment.map_n2_percent = record.map_n2_percent
    experiment.packaging_description = record.packaging_description
    for name in _COMPOSITION:
        setattr(experiment, name, getattr(record.composition, name))
    db.flush()
    return experiment


def _write_ingredients(
    db: Session, experiment: Experiment, record: ExperimentRecord, result: WriteResult,
) -> dict[str, int]:
    """Write the arm's ingredients and their doses. Returns {name: ingredient_id}."""
    by_name: dict[str, int] = {}
    for ingredient_record in record.ingredients:
        ingredient, created = _get_or_create_ingredient(db, ingredient_record)
        by_name[ingredient_record.ingredient_name] = ingredient.id
        if created:
            result.new_terms.append(f"ingredient: {ingredient_record.ingredient_name}")

    for link in record.experiment_ingredients:
        ingredient_id = by_name.get(link.ingredient_name)
        if ingredient_id is None:
            continue
        existing = (
            db.query(ExperimentIngredient)
            .filter(ExperimentIngredient.experiment_id == experiment.id,
                    ExperimentIngredient.ingredient_id == ingredient_id)
            .first()
        )
        if existing:
            existing.concentration_ppm = link.concentration_ppm
            existing.application_method = link.application_method
        else:
            db.add(ExperimentIngredient(
                experiment_id=experiment.id, ingredient_id=ingredient_id,
                concentration_ppm=link.concentration_ppm,
                application_method=link.application_method,
            ))
            result.ingredients += 1
    db.flush()
    return by_name


def _write_measurements(
    db: Session, experiment: Experiment, record: ExperimentRecord, result: WriteResult,
) -> dict[tuple[str, str], int]:
    """Write the arm's indicators and measurements. Returns {(name, unit): indicator_id}."""
    by_key: dict[tuple[str, str], int] = {}
    for indicator_record in record.indicators:
        indicator, created = _get_or_create_indicator(db, indicator_record)
        by_key[(indicator_record.indicator_name, indicator_record.indicator_unit)] = indicator.id
        if created:
            result.new_terms.append(
                f"indicator: {indicator_record.indicator_name} "
                f"({indicator_record.indicator_unit})")

    for measurement in record.measurements:
        indicator_id = by_key.get((measurement.indicator_name, measurement.indicator_unit))
        if indicator_id is None:
            continue
        # (experiment, day, indicator) is the composite primary key; a re-extraction of the
        # same paper updates the value rather than raising on the duplicate.
        existing = (
            db.query(Measurement)
            .filter(Measurement.experiment_id == experiment.id,
                    Measurement.day == measurement.day,
                    Measurement.indicator_id == indicator_id)
            .first()
        )
        if existing:
            existing.indicator_value = measurement.indicator_value
        else:
            db.add(Measurement(
                experiment_id=experiment.id, day=measurement.day, indicator_id=indicator_id,
                indicator_value=measurement.indicator_value,
            ))
            result.measurements += 1
    db.flush()
    return by_key


def write_bundle(
    db: Session,
    *,
    project_id: int,
    paper_id: int,
    job_id: int,
    bundle: GoldBundle,
    evidence_sink: Optional[EvidenceSink] = None,
) -> WriteResult:
    """Persist every arm in the bundle. Returns what was written."""
    result = WriteResult()

    for record in bundle.experiments:
        experiment = _get_or_create_experiment(
            db, project_id=project_id, paper_id=paper_id, job_id=job_id, record=record)
        result.experiments += 1

        _write_ingredients(db, experiment, record, result)
        _write_measurements(db, experiment, record, result)

        if evidence_sink:
            for span in record.evidence:
                evidence_sink("experiment", {"experiment_id": experiment.id},
                              span.field_name, span)
                result.evidence += 1

    if result.new_terms:
        logger.info("Paper %s introduced %d new vocabulary terms", paper_id,
                    len(result.new_terms))
    return result
