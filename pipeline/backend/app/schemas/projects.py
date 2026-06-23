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
    row_count: int = 0

    class Config:
        from_attributes = True
