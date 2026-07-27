"""Extraction endpoints: trigger the mock ETL into the database."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services import ETLService

router = APIRouter(prefix="/extraction", tags=["extraction"])


@router.post("/run")
def run_extraction(db: Session = Depends(get_db)) -> dict:
    """Extract the mock dataset, validate it, and load it into the database."""
    loaded = ETLService(db).load()
    return {"status": "ok", "loaded": loaded}
