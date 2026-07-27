"""Microorganism registry CRUD."""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.models import Microorganism, User
from app.schemas.canonical import MicroorganismCreate, MicroorganismOut, MicroorganismUpdate

router = APIRouter(prefix="/microorganisms", tags=["microorganisms"])


def _get_or_404(micro_id: int, db: Session) -> Microorganism:
    m = db.query(Microorganism).filter(Microorganism.id == micro_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Microorganism not found")
    return m


@router.get("", response_model=list[MicroorganismOut])
def list_microorganisms(
    project_id: Optional[int] = Query(None),
    q: Optional[str] = Query(None, description="Search by canonical name"),
    organism_role: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Microorganism)
    if project_id is not None:
        query = query.filter(
            (Microorganism.project_id == project_id) | (Microorganism.project_id == None)
        )
    if q:
        query = query.filter(Microorganism.canonical_name.ilike(f"%{q}%"))
    if organism_role:
        query = query.filter(Microorganism.organism_role == organism_role)
    return query.order_by(Microorganism.canonical_name).offset(skip).limit(limit).all()


@router.post("", response_model=MicroorganismOut, status_code=status.HTTP_201_CREATED)
def create_microorganism(
    payload: MicroorganismCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = payload.model_dump(exclude={"synonyms"})
    m = Microorganism(**data, synonyms_json=json.dumps(payload.synonyms))
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.get("/{micro_id}", response_model=MicroorganismOut)
def get_microorganism(
    micro_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_or_404(micro_id, db)


@router.patch("/{micro_id}", response_model=MicroorganismOut)
def update_microorganism(
    micro_id: int,
    payload: MicroorganismUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = _get_or_404(micro_id, db)
    data = payload.model_dump(exclude_none=True)
    if "synonyms" in data:
        m.synonyms_json = json.dumps(data.pop("synonyms"))
    for k, v in data.items():
        setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/{micro_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_microorganism(
    micro_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = _get_or_404(micro_id, db)
    db.delete(m)
    db.commit()
