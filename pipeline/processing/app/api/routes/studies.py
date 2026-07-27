"""Studies CRUD — one study per paper (normally)."""

import json
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from shared.auth import get_current_user
from shared.db.database import get_db
from shared.db.models import AuditEvent, Study, User
from shared.schemas.canonical import (
    StudyCreate, StudyDetail, StudyOut, StudyUpdate,
)

from app.services import scoping

router = APIRouter(prefix="/studies", tags=["studies"])


def _get_study_or_404(study_id: int, db: Session, user: User, role: str = "viewer"):
    """Fetch and authorize through the project that owns it."""
    return scoping.require_entity(
        db, Study, study_id, user, label="Study", required_role=role
    )


def _record_audit(db: Session, user: User, entity_id: int, action: str,
                  before: dict | None, after: dict | None, reason: str | None = None):
    diff = {}
    if before and after:
        diff = {k: {"before": before.get(k), "after": after.get(k)}
                for k in set(list(before.keys()) + list(after.keys()))
                if before.get(k) != after.get(k)}
    db.add(AuditEvent(
        actor_id=user.id,
        entity_type="study",
        entity_id=entity_id,
        action=action,
        before_json=json.dumps(before) if before else None,
        after_json=json.dumps(after) if after else None,
        diff_json=json.dumps(diff),
        reason=reason,
        source="user",
    ))


@router.get("", response_model=list[StudyOut])
def list_studies(
    project_id: int = Query(...),
    review_status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = scoping.scope_query(db, db.query(Study), Study.project_id, project_id, current_user)
    if review_status:
        q = q.filter(Study.review_status == review_status)
    return q.order_by(Study.created_at.desc()).offset(skip).limit(limit).all()


@router.post("", response_model=StudyOut, status_code=status.HTTP_201_CREATED)
def create_study(
    payload: StudyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    study = Study(
        **{k: v for k, v in payload.model_dump(exclude={"authors"}).items()},
        authors_json=json.dumps(payload.authors),
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(study)
    db.flush()
    _record_audit(db, current_user, study.id, "create", None, payload.model_dump())
    db.commit()
    db.refresh(study)
    return study


@router.get("/{study_id}", response_model=StudyDetail)
def get_study(
    study_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = _get_study_or_404(study_id, db, current_user)
    return s


@router.patch("/{study_id}", response_model=StudyOut)
def update_study(
    study_id: int,
    payload: StudyUpdate,
    reason: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = _get_study_or_404(study_id, db, current_user)
    before = {"review_status": s.review_status, "title": s.title}
    data = payload.model_dump(exclude_none=True)
    if "authors" in data:
        s.authors_json = json.dumps(data.pop("authors"))
    for k, v in data.items():
        setattr(s, k, v)
    s.updated_by = current_user.id
    s.version += 1
    db.flush()
    _record_audit(db, current_user, study_id, "update", before, data, reason)
    db.commit()
    db.refresh(s)
    return s


@router.post("/{study_id}/approve", response_model=StudyOut)
def approve_study(
    study_id: int,
    reason: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = _get_study_or_404(study_id, db, current_user)
    before_status = s.review_status
    s.review_status = "approved"
    s.updated_by = current_user.id
    s.version += 1
    db.flush()
    _record_audit(db, current_user, study_id, "approve",
                  {"review_status": before_status}, {"review_status": "approved"}, reason)
    db.commit()
    db.refresh(s)
    return s


@router.post("/{study_id}/reject", response_model=StudyOut)
def reject_study(
    study_id: int,
    reason: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = _get_study_or_404(study_id, db, current_user)
    before_status = s.review_status
    s.review_status = "rejected"
    s.updated_by = current_user.id
    s.version += 1
    db.flush()
    _record_audit(db, current_user, study_id, "reject",
                  {"review_status": before_status}, {"review_status": "rejected"}, reason)
    db.commit()
    db.refresh(s)
    return s


@router.delete("/{study_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_study(
    study_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = _get_study_or_404(study_id, db, current_user)
    _record_audit(db, current_user, study_id, "delete",
                  {"review_status": s.review_status, "title": s.title}, None)
    db.delete(s)
    db.commit()
