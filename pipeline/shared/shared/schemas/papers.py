from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class PaperOut(BaseModel):
    id: int
    project_id: int
    filename: str
    original_name: str
    page_count: int
    status: str
    error_message: str
    uploaded_at: datetime
    row_count: int = 0

    class Config:
        from_attributes = True


class ProvenanceInfo(BaseModel):
    page: Optional[int] = None
    table: Optional[str] = None
    confidence: Optional[float] = None


class RowOut(BaseModel):
    id: int
    paper_id: int
    project_id: int
    data: Dict[str, Any]
    provenance: Dict[str, ProvenanceInfo]
    status: str
    reviewer_note: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RowUpdate(BaseModel):
    data: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    reviewer_note: Optional[str] = None


class BulkStatusUpdate(BaseModel):
    row_ids: List[int]
    status: str
