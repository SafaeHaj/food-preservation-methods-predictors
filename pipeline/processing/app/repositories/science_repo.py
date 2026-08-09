"""Queries over the scientific schema — experiments, ingredients, indicators, measurements."""

from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from shared.db.models import (
    Evidence, Experiment, ExperimentIngredient, Indicator, Ingredient,
    Measurement, Paper,
)


def list_experiments(
    db: Session, project_id: int, paper_id: Optional[int] = None
) -> list[Experiment]:
    query = db.query(Experiment).filter(Experiment.project_id == project_id)
    if paper_id is not None:
        query = query.filter(Experiment.paper_id == paper_id)
    return query.order_by(Experiment.id.desc()).all()


def get_experiment(db: Session, project_id: int, experiment_id: int) -> Experiment | None:
    return (
        db.query(Experiment)
        .filter(Experiment.id == experiment_id, Experiment.project_id == project_id)
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
        db.query(ExperimentIngredient, Ingredient)
        .join(Ingredient, Ingredient.id == ExperimentIngredient.ingredient_id)
        .filter(ExperimentIngredient.experiment_id.in_(experiment_ids))
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
        db.query(Measurement.experiment_id, func.count())
        .filter(Measurement.experiment_id.in_(experiment_ids))
        .group_by(Measurement.experiment_id)
        .all()
    )
    counts = {experiment_id: 0 for experiment_id in experiment_ids}
    counts.update(dict(rows))
    return counts


def measurements_for(db: Session, experiment_id: int) -> list[tuple]:
    return (
        db.query(Measurement, Indicator)
        .join(Indicator, Indicator.id == Measurement.indicator_id)
        .filter(Measurement.experiment_id == experiment_id)
        .order_by(Measurement.day, Indicator.indicator_name)
        .all()
    )


def list_ingredients(db: Session, project_id: int) -> list[Ingredient]:
    return (
        db.query(Ingredient)
        .filter(Ingredient.project_id == project_id)
        .order_by(Ingredient.ingredient_name)
        .all()
    )


def list_indicators(db: Session, project_id: int) -> list[Indicator]:
    return (
        db.query(Indicator)
        .filter(Indicator.project_id == project_id)
        .order_by(Indicator.indicator_name)
        .all()
    )


def get_indicator(db: Session, project_id: int, indicator_id: int) -> Indicator | None:
    # Filtered by project, not just id: this backs a write, and an id-only lookup would let
    # one tenant set thresholds on another's indicators.
    return (
        db.query(Indicator)
        .filter(Indicator.id == indicator_id, Indicator.project_id == project_id)
        .first()
    )


def evidence_for_experiment(db: Session, experiment_id: int) -> list[Evidence]:
    """Evidence anchored to one experiment.

    `entity_key` is a JSON string, so this filters in Python after a paper-scoped fetch.
    The previous implementation used `LIKE '%"experiment_id": 1%'`, which also matched
    experiments 10, 12 and 199 -- returning another experiment's provenance as this one's.
    """
    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    if not experiment:
        return []

    candidates = (
        db.query(Evidence).filter(Evidence.paper_id == experiment.paper_id).all()
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


def get_evidence(db: Session, evidence_id: int) -> Evidence | None:
    return db.query(Evidence).filter(Evidence.id == evidence_id).first()


def project_id_for_evidence(db: Session, evidence_id: int) -> int | None:
    """The project that owns an evidence record, via its paper.

    Needed because the evidence endpoints are addressed by a bare id; without this they
    have nothing to authorize against, which is why they previously authorized nothing.
    """
    row = (
        db.query(Paper.project_id)
        .join(Evidence, Evidence.paper_id == Paper.id)
        .filter(Evidence.id == evidence_id)
        .first()
    )
    return row[0] if row else None
