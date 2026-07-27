"""Normalization mappings CRUD + apply endpoint."""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from shared.auth import get_current_user
from shared.db.database import get_db
from shared.errors import ConflictError, NotFoundError
from shared.db.models import NormalizationMapping, User
from shared.schemas.canonical import NormalizationMappingCreate, NormalizationMappingOut

from app.services import scoping

router = APIRouter(prefix="/normalization", tags=["normalization"])


@router.get("/mappings", response_model=list[NormalizationMappingOut])
def list_mappings(
    project_id: Optional[int] = Query(None),
    mapping_type: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # include_shared: site-wide unit and term mappings have no project and apply to all.
    query = scoping.scope_query(
        db, db.query(NormalizationMapping), NormalizationMapping.project_id,
        project_id, current_user, include_shared=True,
    )
    if mapping_type:
        query = query.filter(NormalizationMapping.mapping_type == mapping_type)
    if q:
        query = query.filter(NormalizationMapping.original_term.ilike(f"%{q}%"))
    return query.order_by(NormalizationMapping.mapping_type, NormalizationMapping.original_term)\
                .offset(skip).limit(limit).all()


@router.post("/mappings", response_model=NormalizationMappingOut, status_code=status.HTTP_201_CREATED)
def create_mapping(
    payload: NormalizationMappingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = (db.query(NormalizationMapping)
                  .filter_by(project_id=payload.project_id,
                              mapping_type=payload.mapping_type,
                              original_term=payload.original_term)
                  .first())
    if existing:
        raise ConflictError("Mapping already exists")
    m = NormalizationMapping(**payload.model_dump(), created_by=current_user.id)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = db.query(NormalizationMapping).filter(NormalizationMapping.id == mapping_id).first()
    if not m:
        raise NotFoundError("Mapping not found")
    db.delete(m)
    db.commit()


@router.post("/apply/{project_id}")
def apply_normalization(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger normalization service to apply all mappings to unapplied entities."""
    from app.services.normalization import run_normalization
    result = run_normalization(project_id, db)
    return {"applied": result}
