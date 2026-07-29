"""Queries over the structured extraction output (`ext_*` tables)."""

from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from shared.db.models import (
    ExtEvidence, ExtExperiment, ExtExperimentIngredient, ExtIndicator, ExtIngredient,
    ExtMeasurement, Paper,
)


def list_experiments(
    db: Session, project_id: int, paper_id: Optional[int] = None
) -> list[ExtExperiment]:
    query = db.query(ExtExperiment).filter(ExtExperiment.project_id == project_id)
    if paper_id is not None:
        query = query.filter(ExtExperiment.paper_id == paper_id)
    return query.order_by(ExtExperiment.id.desc()).all()


def get_experiment(db: Session, project_id: int, experiment_id: int) -> ExtExperiment | None:
    return (
        db.query(ExtExperiment)
        .filter(ExtExperiment.id == experiment_id, ExtExperiment.project_id == project_id)
        .first()
    )


def ingredients_for(db: Session, experiment_ids: list[int]) -> dict[int, list[tuple]]:
    """{experiment_id: [(ingredient, link), ...]} in one query.

    Batched: the list endpoint previously ran two queries per experiment, so a project with
    200 experiments issued 400 extra round trips to render one page.
    """
    if not experiment_ids:
        return {}

    rows = (
        db.query(ExtExperimentIngredient, ExtIngredient)
        .join(ExtIngredient, ExtIngredient.id == ExtExperimentIngredient.ingredient_id)
        .filter(ExtExperimentIngredient.experiment_id.in_(experiment_ids))
        .all()
    )
    grouped: dict[int, list[tuple]] = {experiment_id: [] for experiment_id in experiment_ids}
    for link, ingredient in rows:
        grouped[link.experiment_id].append((ingredient, link))
    return grouped


def measurement_counts(db: Session, experiment_ids: list[int]) -> dict[int, int]:
    if not experiment_ids:
        return {}
    rows = (
        db.query(ExtMeasurement.experiment_id, func.count())
        .filter(ExtMeasurement.experiment_id.in_(experiment_ids))
        .group_by(ExtMeasurement.experiment_id)
        .all()
    )
    counts = {experiment_id: 0 for experiment_id in experiment_ids}
    counts.update(dict(rows))
    return counts


def measurements_for(db: Session, experiment_id: int) -> list[tuple]:
    return (
        db.query(ExtMeasurement, ExtIndicator)
        .join(ExtIndicator, ExtIndicator.id == ExtMeasurement.indicator_id)
        .filter(ExtMeasurement.experiment_id == experiment_id)
        .order_by(ExtMeasurement.day, ExtIndicator.indicator_type)
        .all()
    )


def list_ingredients(db: Session, project_id: int) -> list[ExtIngredient]:
    return (
        db.query(ExtIngredient)
        .filter(ExtIngredient.project_id == project_id)
        .order_by(ExtIngredient.ingredient_name)
        .all()
    )


def list_indicators(db: Session, project_id: int) -> list[ExtIndicator]:
    return (
        db.query(ExtIndicator)
        .filter(ExtIndicator.project_id == project_id)
        .order_by(ExtIndicator.indicator_type)
        .all()
    )


def evidence_for_experiment(db: Session, experiment_id: int) -> list[ExtEvidence]:
    """Evidence anchored to one experiment.

    `entity_key` is a JSON string, so this filters in Python after a paper-scoped fetch.
    The previous implementation used `LIKE '%"experiment_id": 1%'`, which also matched
    experiments 10, 12 and 199 -- returning another experiment's provenance as this one's.
    """
    experiment = db.query(ExtExperiment).filter(ExtExperiment.id == experiment_id).first()
    if not experiment:
        return []

    candidates = (
        db.query(ExtEvidence).filter(ExtEvidence.paper_id == experiment.paper_id).all()
    )
    matched = []
    for record in candidates:
        try:
            key = json.loads(record.entity_key) if record.entity_key else {}
        except (TypeError, ValueError):
            continue
        if key.get("experiment_id") == experiment_id:
            matched.append(record)
    return matched


def get_evidence(db: Session, evidence_id: int) -> ExtEvidence | None:
    return db.query(ExtEvidence).filter(ExtEvidence.id == evidence_id).first()


def project_id_for_evidence(db: Session, evidence_id: int) -> int | None:
    """The project that owns an evidence record, via its paper.

    Needed because the evidence endpoints are addressed by a bare id; without this they
    have nothing to authorize against, which is why they previously authorized nothing.
    """
    row = (
        db.query(Paper.project_id)
        .join(ExtEvidence, ExtEvidence.paper_id == Paper.id)
        .filter(ExtEvidence.id == evidence_id)
        .first()
    )
    return row[0] if row else None
