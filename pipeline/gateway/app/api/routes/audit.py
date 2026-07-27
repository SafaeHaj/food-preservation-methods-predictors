"""Audit event log -- read-only, scoped to projects the caller can see."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from shared.access import authorize_project
from shared.db.models import AuditEvent, ProjectMember, User
from shared.db.database import get_db
from shared.schemas.canonical import AuditEventOut

from app.api.deps import get_current_user

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditEventOut])
def list_audit_events(
    project_id: Optional[int] = Query(None),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    actor_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(AuditEvent)

    # Previously unscoped: omitting project_id returned every project's audit trail,
    # including who changed what in projects the caller has no access to.
    if project_id is not None:
        authorize_project(db, project_id, user)
        query = query.filter(AuditEvent.project_id == project_id)
    else:
        # scalar_subquery(), not subquery(): IN () needs a single-column SELECT, and
        # passing a Subquery makes SQLAlchemy coerce it with a warning.
        visible = (
            db.query(ProjectMember.project_id)
            .filter(ProjectMember.user_id == user.id)
            .scalar_subquery()
        )
        query = query.filter(AuditEvent.project_id.in_(visible))

    if entity_type:
        query = query.filter(AuditEvent.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditEvent.entity_id == entity_id)
    if action:
        query = query.filter(AuditEvent.action == action)
    if actor_id:
        query = query.filter(AuditEvent.actor_id == actor_id)

    events = query.order_by(AuditEvent.created_at.desc()).offset(skip).limit(limit).all()
    return [
        AuditEventOut(
            id=event.id,
            actor_id=event.actor_id,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            action=event.action,
            diff=json.loads(event.diff_json) if event.diff_json else None,
            reason=event.reason,
            source=event.source,
            project_id=event.project_id,
            created_at=event.created_at,
        )
        for event in events
    ]
