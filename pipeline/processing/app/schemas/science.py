"""Request and response models for the scientific schema."""

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
    #: What the paper calls it, e.g. "Total viable count". This is the label to show.
    indicator_name: str
    #: The category it belongs to: "microbial" or "chemical". Not a display name.
    indicator_type: str
    indicator_unit: str
    indicator_threshold: Optional[float] = None


class IndicatorUpdate(BaseModel):
    """The threshold only.

    Name, type and unit are extraction output and identify the row -- name and unit form
    its uniqueness constraint -- so editing them here would either collide with another
    indicator or silently relabel every measurement pointing at this one.
    """

    indicator_threshold: Optional[float] = None


class ExperimentIngredientOut(BaseModel):
    ingredient_id: int
    ingredient_name: str
    functional_class: str
    source: str
    #: Null when the paper names the additive without stating how much was used.
    concentration: Optional[float] = None
    concentration_unit: Optional[str] = None


class MeasurementOut(BaseModel):
    day: int
    indicator_id: int
    indicator_name: str
    indicator_type: str
    indicator_unit: str
    indicator_threshold: Optional[float] = None
    indicator_value: float
    #: How many separately-printed readings were averaged into this value; 1 when the paper
    #: printed a single value or its own mean.
    replicates: int = 1


class BoundingBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class EvidenceOut(BaseModel):
    id: int
    entity_type: str
    entity_key: dict[str, Any]
    field_name: str
    page_number: Optional[int] = None
    source_type: str
    source_label: Optional[str] = None
    exact_text: Optional[str] = None
    #: How the value was arrived at: "stated", "derived" or "inferred". The last two carry
    #: a `rationale`, so a computed value is never read as one the paper stated outright.
    method: str
    rationale: Optional[str] = None
    bounding_box: Optional[BoundingBox] = None
    #: Scored by the pipeline against the source text, never supplied by the model.
    confidence: Optional[float] = None
    figure_series: Optional[str] = None
    x_axis_value: Optional[float] = None
    y_axis_value: Optional[float] = None
    value_is_approximate: bool = False
    is_chart_derived: bool = False


class ExperimentSummaryOut(BaseModel):
    id: int
    paper_id: int
    meat_matrix: str
    #: Null when the paper never describes this arm's handling. Whether it addressed it at
    #: all is answered by an evidence span for `field_name="treatment"`, not by this field.
    treatment: Optional[str] = None
    weight_g: Optional[float] = None
    ingredients: list[ExperimentIngredientOut]
    measurement_count: int
    created_at: Optional[datetime] = None


class ExperimentDetailOut(BaseModel):
    id: int
    paper_id: int
    meat_matrix: str
    treatment: Optional[str] = None
    weight_g: Optional[float] = None
    created_at: Optional[datetime] = None
    ingredients: list[ExperimentIngredientOut]
    measurements: list[MeasurementOut]
    evidence: list[EvidenceOut]
