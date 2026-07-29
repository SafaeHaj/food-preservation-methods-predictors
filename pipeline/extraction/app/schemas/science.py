"""Response models for the structured extraction output (`ext_*` tables)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class IngredientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ingredient_name: str
    functional_class: str
    source: str


class IndicatorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    indicator_type: str
    indicator_unit: str
    indicator_threshold: Optional[float] = None


class ExperimentIngredientOut(BaseModel):
    ingredient_id: int
    ingredient_name: str
    functional_class: str
    source: str
    concentration: float
    concentration_unit: str


class MeasurementOut(BaseModel):
    day: int
    indicator_id: int
    indicator_type: str
    indicator_unit: str
    indicator_threshold: Optional[float] = None
    indicator_value: float
    value_is_approximate: bool = False


class BoundingBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class EvidenceOut(BaseModel):
    id: int
    entity_type: str
    entity_key: dict[str, Any]
    field_name: Optional[str] = None
    page_number: Optional[int] = None
    source_type: str
    source_label: Optional[str] = None
    exact_text: Optional[str] = None
    bounding_box: Optional[BoundingBox] = None
    confidence: Optional[float] = None
    figure_series: Optional[str] = None
    x_axis_value: Optional[float] = None
    y_axis_value: Optional[float] = None
    value_is_approximate: bool = False
    is_chart_derived: bool = False
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None


class ExperimentSummaryOut(BaseModel):
    id: int
    paper_id: int
    meat_matrix: str
    treatment: str
    ingredients: list[ExperimentIngredientOut]
    measurement_count: int
    created_at: Optional[datetime] = None


class ExperimentDetailOut(BaseModel):
    id: int
    paper_id: int
    meat_matrix: str
    treatment: str
    created_at: Optional[datetime] = None
    ingredients: list[ExperimentIngredientOut]
    measurements: list[MeasurementOut]
    evidence: list[EvidenceOut]
