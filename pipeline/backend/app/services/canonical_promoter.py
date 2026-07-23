"""
Promote legacy ExtractedRow records to the canonical scientific data hierarchy:
  Study → Experiment → TreatmentArm → Observation

Called automatically at the end of PDF extraction so that canonical pages
(Studies, Experiments, Dataset) are populated immediately after extraction.
The function is idempotent: it checks for existing records before creating.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import (
    Experiment, ExtractedRow, Observation, Paper, Study, TreatmentArm,
)


def _safe_float(val) -> Optional[float]:
    try:
        return float(val) if val not in (None, "", "N/A", "n/a", "NR") else None
    except (ValueError, TypeError):
        return None


def _get_or_create_study(paper: Paper, project_id: int, db: Session) -> Study:
    """One Study per paper — idempotent."""
    existing = db.query(Study).filter(Study.paper_id == paper.id).first()
    if existing:
        return existing
    # Derive a readable title from the filename
    raw = paper.original_name.rsplit(".", 1)[0]
    title = raw.replace("_", " ").replace("-", " ").strip() or f"Study from {paper.original_name}"
    study = Study(
        project_id=project_id,
        paper_id=paper.id,
        title=title,
        authors_json="[]",
        notes="Auto-promoted from extracted PDF rows. Review and update metadata.",
        review_status="extracted",
    )
    db.add(study)
    db.flush()
    return study


def _get_or_create_experiment(
    study_id: int,
    product_type: Optional[str],
    temperature_c: Optional[float],
    db: Session,
) -> Experiment:
    """One Experiment per unique (study, product_type, temperature_c) — idempotent."""
    q = db.query(Experiment).filter(Experiment.study_id == study_id)
    if product_type:
        q = q.filter(Experiment.product_name_original == product_type)
    else:
        q = q.filter(Experiment.product_name_original == None)
    if temperature_c is not None:
        q = q.filter(Experiment.storage_temperature_c == temperature_c)
    else:
        q = q.filter(Experiment.storage_temperature_c == None)
    existing = q.first()
    if existing:
        return existing

    # Map product_type to food_category heuristically
    cat = "other"
    if product_type:
        pt = product_type.lower()
        for keyword, category in [
            ("cheese", "cheese"), ("meat", "meat"), ("beef", "meat"), ("pork", "meat"),
            ("poultry", "poultry"), ("chicken", "poultry"), ("turkey", "poultry"),
            ("fish", "seafood"), ("seafood", "seafood"), ("shrimp", "seafood"),
            ("milk", "dairy"), ("dairy", "dairy"), ("yogurt", "dairy"),
            ("vegetable", "produce"), ("fruit", "produce"), ("salad", "produce"),
            ("bread", "bakery"), ("bakery", "bakery"),
            ("juice", "beverage"), ("drink", "beverage"),
        ]:
            if keyword in pt:
                cat = category
                break

    exp = Experiment(
        study_id=study_id,
        product_name_original=product_type,
        food_category=cat,
        storage_temperature_c=temperature_c,
        gas_composition_json="{}",
        extra_conditions_json="{}",
        review_status="extracted",
    )
    db.add(exp)
    db.flush()
    return exp


def _get_or_create_arm(
    experiment_id: int,
    ingredient: Optional[str],
    concentration: Optional[float],
    conc_unit: Optional[str],
    db: Session,
) -> TreatmentArm:
    """One TreatmentArm per unique (experiment, ingredient, concentration) — idempotent."""
    q = db.query(TreatmentArm).filter(TreatmentArm.experiment_id == experiment_id)
    if ingredient:
        q = q.filter(TreatmentArm.ingredient_name_original == ingredient)
    else:
        q = q.filter(TreatmentArm.ingredient_name_original == None)
    if concentration is not None:
        q = q.filter(TreatmentArm.concentration_value_original == concentration)
    else:
        q = q.filter(TreatmentArm.concentration_value_original == None)
    existing = q.first()
    if existing:
        return existing

    is_ctrl = (
        not ingredient
        or ingredient.lower() in ("control", "untreated", "none", "water", "vehicle")
    )

    arm = TreatmentArm(
        experiment_id=experiment_id,
        ingredient_name_original=ingredient,
        ingredient_name_normalized=ingredient,
        concentration_value_original=concentration,
        concentration_unit_original=conc_unit,
        is_control=is_ctrl,
        treatment_type="antimicrobial" if ingredient and not is_ctrl else "untreated_control",
        combination_treatments_json="[]",
        extra_treatment_json="{}",
        review_status="extracted",
    )
    db.add(arm)
    db.flush()
    return arm


def promote_paper_to_canonical(paper_id: int, project_id: int, db: Session) -> dict:
    """
    Convert all ExtractedRow records for a paper into canonical entities.
    Returns counts of created records.
    """
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        return {"error": "paper not found"}

    rows = db.query(ExtractedRow).filter(
        ExtractedRow.paper_id == paper_id
    ).all()

    if not rows:
        # Still create a stub Study so the paper appears in Studies page
        study = _get_or_create_study(paper, project_id, db)
        db.commit()
        return {"studies": 1, "experiments": 0, "arms": 0, "observations": 0}

    study = _get_or_create_study(paper, project_id, db)
    created = {"studies": 1, "experiments": 0, "arms": 0, "observations": 0}
    _seen_exps: set[int] = set()
    _seen_arms: set[int] = set()

    for row in rows:
        data = row.data
        if not isinstance(data, dict):
            continue

        product_type = data.get("product_type") or None
        temperature_c = _safe_float(data.get("temperature_c"))
        ingredient = data.get("ingredient_name") or None
        concentration = _safe_float(data.get("concentration"))
        conc_unit = data.get("concentration_unit") or None
        microbial_indicator = data.get("microbial_indicator") or None
        initial_count = _safe_float(data.get("initial_count_log_cfu_g"))
        treatment_day = _safe_float(data.get("treatment_day"))
        final_count = _safe_float(data.get("final_count_log_cfu_g"))
        doi = data.get("doi")

        if doi and not study.doi_original:
            study.doi_original = doi

        experiment = _get_or_create_experiment(study.id, product_type, temperature_c, db)
        arm = _get_or_create_arm(experiment.id, ingredient, concentration, conc_unit, db)
        if experiment.id not in _seen_exps:
            _seen_exps.add(experiment.id)
            created["experiments"] += 1
        if arm.id not in _seen_arms:
            _seen_arms.add(arm.id)
            created["arms"] += 1

        # Initial count observation (time = 0)
        if initial_count is not None:
            db.add(Observation(
                treatment_arm_id=arm.id,
                measurement_type="microbial_count",
                measurement_subtype=microbial_indicator,
                time_value_original=0.0,
                time_unit_original="days",
                time_days=0.0,
                numeric_value_original=initial_count,
                numeric_value_normalized=initial_count,
                unit_original="log CFU/g",
                unit_normalized="log CFU/g",
                value_origin="reported_table",
                review_status="extracted",
                is_imputed=False,
                is_derived=False,
                censoring_type="none",
            ))
            created["observations"] += 1

        # Final count observation (time = treatment_day)
        if final_count is not None and treatment_day is not None:
            db.add(Observation(
                treatment_arm_id=arm.id,
                measurement_type="microbial_count",
                measurement_subtype=microbial_indicator,
                time_value_original=treatment_day,
                time_unit_original="days",
                time_days=treatment_day,
                numeric_value_original=final_count,
                numeric_value_normalized=final_count,
                unit_original="log CFU/g",
                unit_normalized="log CFU/g",
                value_origin="reported_table",
                review_status="extracted",
                is_imputed=False,
                is_derived=False,
                censoring_type="none",
            ))
            created["observations"] += 1

    db.commit()
    return created
