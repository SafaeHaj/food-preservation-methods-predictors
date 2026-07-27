"""Schema inference route -- bind HTTP to `schema_inference`, nothing more."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, File, UploadFile

from shared.db.models import User
from shared.schemas.projects import SchemaField

from app.api.deps import get_current_user
from app.services import schema_inference

router = APIRouter(prefix="/schema", tags=["schema"])


@router.post("/infer", response_model=List[SchemaField])
async def infer_schema(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Infer schema fields from an uploaded spreadsheet's columns."""
    return schema_inference.infer_fields(file.filename or "", await file.read())
