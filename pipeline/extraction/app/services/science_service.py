"""Access to the scientific schema — read throughout, plus the indicator threshold edit."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from shared.access import authorize_project
from shared.config import get_common_settings, get_gateway_settings
from shared.db.models import Evidence, Experiment, User
from shared.errors import NotFoundError
from shared.signing import sign_path
from shared.uow import unit_of_work

from app.repositories import science_repo
from app.schemas.science import (
    BoundingBox, EvidenceOut, ExperimentDetailOut, ExperimentIngredientOut,
    ExperimentSummaryOut, IndicatorOut, IndicatorUpdate, IngredientOut, MeasurementOut,
)

logger = logging.getLogger(__name__)

_common = get_common_settings()
_gateway = get_gateway_settings()


def _ingredient_entries(pairs: list[tuple]) -> list[ExperimentIngredientOut]:
    return [
        ExperimentIngredientOut(
            ingredient_id=ingredient.id,
            ingredient_name=ingredient.ingredient_name,
            functional_class=ingredient.functional_class,
            source=ingredient.source,
            concentration=link.concentration,
            concentration_unit=link.concentration_unit,
        )
        for ingredient, link in pairs
    ]


def _measurement_entries(rows: list[tuple]) -> list[MeasurementOut]:
    return [
        MeasurementOut(
            day=measurement.day,
            indicator_id=indicator.id,
            indicator_type=indicator.indicator_type,
            indicator_unit=indicator.indicator_unit,
            indicator_threshold=indicator.indicator_threshold,
            indicator_value=measurement.indicator_value,
            value_is_approximate=bool(measurement.value_is_approximate),
        )
        for measurement, indicator in rows
    ]


def _evidence_out(record: Evidence) -> EvidenceOut:
    try:
        entity_key = json.loads(record.entity_key) if record.entity_key else {}
    except (TypeError, ValueError):
        entity_key = {}

    box = (
        BoundingBox(x1=record.bbox_x1, y1=record.bbox_y1, x2=record.bbox_x2, y2=record.bbox_y2)
        if record.bbox_x1 is not None and record.bbox_y1 is not None
        and record.bbox_x2 is not None and record.bbox_y2 is not None
        else None
    )

    ttl = _gateway.ASSET_URL_TTL_SECONDS
    base = f"/api/evidence/{record.id}"
    has_image = bool(record.evidence_image_path and Path(record.evidence_image_path).exists())
    has_thumb = bool(
        record.evidence_thumbnail_path and Path(record.evidence_thumbnail_path).exists()
    )

    return EvidenceOut(
        id=record.id,
        entity_type=record.entity_type,
        entity_key=entity_key,
        field_name=record.field_name,
        page_number=record.page_number,
        source_type=record.source_type,
        source_label=record.source_label,
        exact_text=record.exact_text,
        bounding_box=box,
        confidence=record.confidence,
        figure_series=record.figure_series,
        x_axis_value=record.x_axis_value,
        y_axis_value=record.y_axis_value,
        value_is_approximate=bool(record.value_is_approximate),
        is_chart_derived=bool(record.is_chart_derived),
        image_url=sign_path(_common.SECRET_KEY, f"{base}/image", ttl) if has_image else None,
        thumbnail_url=(
            sign_path(_common.SECRET_KEY, f"{base}/thumbnail", ttl) if has_thumb else None
        ),
    )


def list_experiments(
    db: Session, project_id: int, paper_id: Optional[int] = None
) -> list[ExperimentSummaryOut]:
    experiments = science_repo.list_experiments(db, project_id, paper_id)
    experiment_ids = [experiment.id for experiment in experiments]
    ingredients = science_repo.ingredients_for(db, experiment_ids)
    counts = science_repo.measurement_counts(db, experiment_ids)

    return [
        ExperimentSummaryOut(
            id=experiment.id,
            paper_id=experiment.paper_id,
            meat_matrix=experiment.meat_matrix,
            treatment=experiment.treatment,
            ingredients=_ingredient_entries(ingredients.get(experiment.id, [])),
            measurement_count=counts.get(experiment.id, 0),
            created_at=experiment.created_at,
        )
        for experiment in experiments
    ]


def _require_experiment(db: Session, project_id: int, experiment_id: int) -> Experiment:
    experiment = science_repo.get_experiment(db, project_id, experiment_id)
    if not experiment:
        raise NotFoundError.for_resource("Experiment", experiment_id)
    return experiment


def get_experiment(db: Session, project_id: int, experiment_id: int) -> ExperimentDetailOut:
    experiment = _require_experiment(db, project_id, experiment_id)
    ingredients = science_repo.ingredients_for(db, [experiment_id])

    return ExperimentDetailOut(
        id=experiment.id,
        paper_id=experiment.paper_id,
        meat_matrix=experiment.meat_matrix,
        treatment=experiment.treatment,
        created_at=experiment.created_at,
        ingredients=_ingredient_entries(ingredients.get(experiment_id, [])),
        measurements=_measurement_entries(science_repo.measurements_for(db, experiment_id)),
        evidence=[
            _evidence_out(record)
            for record in science_repo.evidence_for_experiment(db, experiment_id)
        ],
    )


def list_measurements(db: Session, project_id: int, experiment_id: int) -> list[MeasurementOut]:
    _require_experiment(db, project_id, experiment_id)
    return _measurement_entries(science_repo.measurements_for(db, experiment_id))


def list_ingredients(db: Session, project_id: int) -> list[IngredientOut]:
    return [IngredientOut.model_validate(row) for row in science_repo.list_ingredients(db, project_id)]


def list_indicators(db: Session, project_id: int) -> list[IndicatorOut]:
    return [IndicatorOut.model_validate(row) for row in science_repo.list_indicators(db, project_id)]


def update_indicator(
    db: Session, project_id: int, indicator_id: int, body: IndicatorUpdate
) -> IndicatorOut:
    """Edit an indicator's threshold.

    The threshold is the one field on the scientific schema a human is expected to set
    rather than the LLM: papers rarely state the regulatory limit their measurements are
    judged against, and shelf life is defined as the day that limit is crossed. Clearing it
    back to null is a real edit, hence `exclude_unset` rather than a None check.
    """
    indicator = science_repo.get_indicator(db, project_id, indicator_id)
    if not indicator:
        raise NotFoundError.for_resource("Indicator", indicator_id)

    with unit_of_work(db):
        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(indicator, field, value)

    return IndicatorOut.model_validate(indicator)


def get_evidence(db: Session, evidence_id: int, user: User) -> EvidenceOut:
    """Fetch one evidence record, authorized through the project that owns its paper.

    Previously unauthorized entirely: `/api/evidence/{id}` served any record to any
    authenticated user, including the extracted text of other tenants' papers.
    """
    project_id = science_repo.project_id_for_evidence(db, evidence_id)
    if project_id is None:
        raise NotFoundError.for_resource("Evidence record", evidence_id)
    authorize_project(db, project_id, user)

    record = science_repo.get_evidence(db, evidence_id)
    if not record:
        raise NotFoundError.for_resource("Evidence record", evidence_id)
    return _evidence_out(record)


def get_evidence_file(db: Session, evidence_id: int, thumbnail: bool) -> Path:
    """Resolve an evidence crop to disk. Authorized by the URL signature."""
    record = science_repo.get_evidence(db, evidence_id)
    stored = (record.evidence_thumbnail_path if thumbnail else record.evidence_image_path) if record else None
    if not stored or not Path(stored).exists():
        raise NotFoundError("No image is available for this evidence record")
    return Path(stored)
