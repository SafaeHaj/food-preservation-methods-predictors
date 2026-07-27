"""Promote extracted data into the canonical scientific hierarchy.

    Paper -> Study -> Experiment -> TreatmentArm -> Observation

This is the *only* automated writer of that hierarchy; everything else is manual curation
through the UI. It previously read `ExtractedRow` (the flat, free-schema legacy table),
which meant the modern Docling/LLM pipeline -- writing the structured `ext_*` tables --
fed nothing, and the canonical pages stayed empty unless someone ran the old extractor and
then clicked "promote". Reading `ext_*` instead collapses the two ingestion trees into one:
the LLM job promotes as its final step, and the canonical pages are populated by the same
action that produced the data.

Source shape (`ext_*`)::

    ExtExperiment (meat_matrix, treatment) --< ExtExperimentIngredient >-- ExtIngredient
                  \\--< ExtMeasurement (day, indicator_value) >-- ExtIndicator

Target shape: one `Experiment` per distinct `meat_matrix` in the paper, one `TreatmentArm`
per `ExtExperiment` row (i.e. per treatment applied to that matrix), one `Observation` per
`ExtMeasurement`.

Idempotent throughout: re-running after a re-extraction updates rather than duplicates, so
a retried job cannot fork the hierarchy.
"""

from __future__ import annotations

import json
import logging
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from shared.db.models import (
    Experiment, ExtExperiment, ExtExperimentIngredient, ExtIndicator, ExtIngredient,
    ExtMeasurement, Observation, Paper, Study, TreatmentArm,
)
from shared.errors import NotFoundError

logger = logging.getLogger(__name__)

#: meat_matrix substring -> canonical `Experiment.food_category`. First match wins, so more
#: specific keywords must precede general ones.
FOOD_CATEGORY_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("cheese", "cheese"),
    ("yogurt", "dairy"), ("milk", "dairy"), ("dairy", "dairy"),
    ("chicken", "poultry"), ("turkey", "poultry"), ("poultry", "poultry"),
    ("shrimp", "seafood"), ("fish", "seafood"), ("seafood", "seafood"),
    ("salmon", "seafood"), ("prawn", "seafood"),
    ("beef", "meat"), ("pork", "meat"), ("lamb", "meat"), ("sausage", "meat"),
    ("ham", "meat"), ("meat", "meat"),
    ("salad", "produce"), ("vegetable", "produce"), ("fruit", "produce"),
    ("bread", "bakery"), ("bakery", "bakery"),
    ("juice", "beverage"), ("drink", "beverage"),
)

#: indicator_type substring -> canonical `Observation.measurement_type`, drawn from the
#: vocabulary declared on the Observation model. Anything unmatched becomes "other" rather
#: than being silently mislabelled as a microbial count.
INDICATOR_TYPE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("tbars", "TBARS"), ("tba", "TBA"),
    ("tvb", "TVB_N"), ("volatile basic", "TVB_N"),
    ("peroxide", "PV"),
    ("water activity", "water_activity"), ("aw", "water_activity"),
    ("moisture", "moisture"),
    ("sensory", "sensory"), ("texture", "texture"),
    ("weight loss", "weight_loss"), ("protein", "protein"),
    ("ph", "ph"),
    ("count", "microbial_count"), ("cfu", "microbial_count"),
    ("aerobic", "microbial_count"), ("mesophil", "microbial_count"),
    ("psychrotroph", "microbial_count"), ("coliform", "microbial_count"),
    ("lactic", "microbial_count"), ("yeast", "microbial_count"),
    ("mould", "microbial_count"), ("mold", "microbial_count"),
    ("bacteri", "microbial_count"), ("listeria", "microbial_count"),
    ("salmonella", "microbial_count"), ("staphyloc", "microbial_count"),
    ("escherichia", "microbial_count"), ("e. coli", "microbial_count"),
)

#: Treatment labels that denote an untreated reference arm rather than an intervention.
CONTROL_LABELS = frozenset({"control", "untreated", "none", "water", "vehicle", "blank", "ctrl"})


def _classify(value: Optional[str], table: Iterable[tuple[str, str]], default: str) -> str:
    if not value:
        return default
    lowered = value.lower()
    for keyword, category in table:
        if keyword in lowered:
            return category
    return default


def food_category_for(meat_matrix: Optional[str]) -> str:
    return _classify(meat_matrix, FOOD_CATEGORY_KEYWORDS, "other")


def measurement_type_for(indicator_type: Optional[str]) -> str:
    return _classify(indicator_type, INDICATOR_TYPE_KEYWORDS, "other")


def is_control_treatment(treatment: Optional[str]) -> bool:
    if not treatment:
        return True
    return treatment.strip().lower() in CONTROL_LABELS


# ─── Entity resolution (each get-or-create is idempotent) ─────────────────────

def _get_or_create_study(db: Session, paper: Paper, project_id: int) -> Study:
    """One Study per paper."""
    study = db.query(Study).filter(Study.paper_id == paper.id).first()
    if study:
        return study

    stem = paper.original_name.rsplit(".", 1)[0]
    title = stem.replace("_", " ").replace("-", " ").strip() or paper.original_name
    study = Study(
        project_id=project_id,
        paper_id=paper.id,
        title=title,
        authors_json="[]",
        notes="Auto-promoted from the extraction pipeline. Review and complete the metadata.",
        review_status="extracted",
    )
    db.add(study)
    db.flush()
    return study


def _get_or_create_experiment(db: Session, study_id: int, meat_matrix: str) -> Experiment:
    """One Experiment per distinct food matrix within a study.

    `ext_*` carries no storage temperature, so that stays null for a curator to fill in;
    inventing a default would be indistinguishable from extracted fact downstream.
    """
    experiment = (
        db.query(Experiment)
        .filter(
            Experiment.study_id == study_id,
            Experiment.product_name_original == meat_matrix,
        )
        .first()
    )
    if experiment:
        return experiment

    experiment = Experiment(
        study_id=study_id,
        product_name_original=meat_matrix,
        food_category=food_category_for(meat_matrix),
        gas_composition_json="{}",
        extra_conditions_json="{}",
        review_status="extracted",
    )
    db.add(experiment)
    db.flush()
    return experiment


def _get_or_create_arm(
    db: Session, experiment_id: int, ext_experiment: ExtExperiment
) -> TreatmentArm:
    """One TreatmentArm per `ext_experiments` row, carrying its ingredient dosing.

    An `ext_experiment` may link several ingredients (a combination treatment). The first
    becomes the arm's primary ingredient; the remainder are recorded in
    `combination_treatments_json` so no dosing information is lost.
    """
    treatment = ext_experiment.treatment
    arm = (
        db.query(TreatmentArm)
        .filter(
            TreatmentArm.experiment_id == experiment_id,
            TreatmentArm.ingredient_name_original == treatment,
        )
        .first()
    )

    links = (
        db.query(ExtExperimentIngredient, ExtIngredient)
        .join(ExtIngredient, ExtIngredient.id == ExtExperimentIngredient.ingredient_id)
        .filter(ExtExperimentIngredient.experiment_id == ext_experiment.id)
        .all()
    )
    primary_link, primary_ingredient = links[0] if links else (None, None)
    combination = [
        {
            "ingredient": ingredient.ingredient_name,
            "functional_class": ingredient.functional_class,
            "concentration": link.concentration,
            "unit": link.concentration_unit,
        }
        for link, ingredient in links[1:]
    ]

    is_control = is_control_treatment(treatment) and not links
    fields = {
        "ingredient_name_normalized": primary_ingredient.ingredient_name if primary_ingredient else None,
        "concentration_value_original": primary_link.concentration if primary_link else None,
        "concentration_unit_original": primary_link.concentration_unit if primary_link else None,
        "is_control": is_control,
        "treatment_type": "untreated_control" if is_control else "antimicrobial",
        "combination_treatments_json": json.dumps(combination),
    }

    if arm:
        # Re-extraction may have corrected the dosing; keep the arm, refresh its facts.
        for key, value in fields.items():
            setattr(arm, key, value)
        return arm

    arm = TreatmentArm(
        experiment_id=experiment_id,
        ingredient_name_original=treatment,
        extra_treatment_json="{}",
        review_status="extracted",
        **fields,
    )
    db.add(arm)
    db.flush()
    return arm


def _upsert_observation(
    db: Session,
    arm_id: int,
    measurement: ExtMeasurement,
    indicator: ExtIndicator,
) -> bool:
    """Create or refresh the Observation for one measurement. Returns True if created."""
    measurement_type = measurement_type_for(indicator.indicator_type)
    day = float(measurement.day)

    existing = (
        db.query(Observation)
        .filter(
            Observation.treatment_arm_id == arm_id,
            Observation.measurement_type == measurement_type,
            Observation.measurement_subtype == indicator.indicator_type,
            Observation.time_days == day,
        )
        .first()
    )

    # A value read off a chart is an estimate, and downstream modelling weights it
    # differently from a tabulated one -- so the distinction must survive promotion.
    value_origin = "graph_estimated" if measurement.value_is_approximate else "reported_table"

    if existing:
        existing.numeric_value_original = measurement.indicator_value
        existing.numeric_value_normalized = measurement.indicator_value
        existing.value_origin = value_origin
        return False

    db.add(
        Observation(
            treatment_arm_id=arm_id,
            measurement_type=measurement_type,
            measurement_subtype=indicator.indicator_type,
            time_value_original=day,
            time_unit_original="days",
            time_days=day,
            numeric_value_original=measurement.indicator_value,
            numeric_value_normalized=measurement.indicator_value,
            unit_original=indicator.indicator_unit,
            unit_normalized=indicator.indicator_unit,
            value_origin=value_origin,
            review_status="extracted",
            is_imputed=False,
            is_derived=False,
            censoring_type="none",
        )
    )
    return True


# ─── Entry point ──────────────────────────────────────────────────────────────

def promote_paper_to_canonical(paper_id: int, project_id: int, db: Session) -> dict:
    """Promote one paper's `ext_*` extraction into the canonical hierarchy.

    Returns counts of entities created. Does **not** commit: the caller owns the
    transaction (`shared.uow.unit_of_work`), so promotion either lands whole or not at all.
    """
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise NotFoundError.for_resource("Paper", paper_id)

    study = _get_or_create_study(db, paper, project_id)
    created = {"studies": 1, "experiments": 0, "arms": 0, "observations": 0}

    ext_experiments = (
        db.query(ExtExperiment)
        .filter(ExtExperiment.paper_id == paper_id)
        .order_by(ExtExperiment.id)
        .all()
    )
    if not ext_experiments:
        # A stub Study still gets created so the paper is visible on the Studies page and
        # a curator can see that extraction produced nothing.
        logger.info("Paper %s has no ext_experiments; promoted a stub study only", paper_id)
        return created

    seen_experiments: set[int] = set()
    seen_arms: set[int] = set()

    for ext_experiment in ext_experiments:
        experiment = _get_or_create_experiment(db, study.id, ext_experiment.meat_matrix)
        if experiment.id not in seen_experiments:
            seen_experiments.add(experiment.id)
            created["experiments"] += 1

        arm = _get_or_create_arm(db, experiment.id, ext_experiment)
        if arm.id not in seen_arms:
            seen_arms.add(arm.id)
            created["arms"] += 1

        measurements = (
            db.query(ExtMeasurement, ExtIndicator)
            .join(ExtIndicator, ExtIndicator.id == ExtMeasurement.indicator_id)
            .filter(ExtMeasurement.experiment_id == ext_experiment.id)
            .order_by(ExtMeasurement.day)
            .all()
        )
        for measurement, indicator in measurements:
            if _upsert_observation(db, arm.id, measurement, indicator):
                created["observations"] += 1

    logger.info("Promoted paper %s: %s", paper_id, created)
    return created
