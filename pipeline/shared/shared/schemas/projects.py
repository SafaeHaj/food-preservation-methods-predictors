from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel


class SchemaField(BaseModel):
    name: str
    label: str
    type: str  # text | number | select | boolean
    unit: Optional[str] = None
    options: Optional[List[str]] = None  # for select
    required: bool = False
    validation: Optional[dict] = None   # {min, max} for numbers


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    schema_fields: List[SchemaField] = []


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    schema_fields: Optional[List[SchemaField]] = None


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str
    schema_fields: List[SchemaField]
    created_at: datetime
    updated_at: datetime
    owner_id: int
    paper_count: int = 0
    #: The caller's role on this project ("owner" | "admin" | "reviewer" | "analyst" |
    #: "viewer"), so the UI can hide actions it would only be refused for.
    your_role: str = "viewer"

    class Config:
        from_attributes = True


class ProjectStats(BaseModel):
    """Aggregates for the project overview.

    Counted over the scientific schema. The previous set (`study_count`, `observation_count`,
    `approved_count`, `needs_review_count`) counted rows in the parallel hierarchy that has
    since been deleted, and the two review counters described a per-row approval workflow
    that no longer exists -- curation happens on the validation screen, before the LLM runs.
    """

    paper_count: int = 0
    experiment_count: int = 0
    measurement_count: int = 0
    ingredient_count: int = 0
    indicator_count: int = 0
    #: Indicators carrying a threshold. Shelf life is the day a threshold is crossed, so
    #: this is the count that says whether the project can be modelled at all.
    indicators_with_threshold: int = 0
    member_count: int = 0
    last_extraction_at: Optional[str] = None
