"""Audit event log — read-only."""

import json
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.models import AuditEvent, User
from app.schemas.canonical import AuditEventOut

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
    current_user: User = Depends(get_current_user),
):
    q = db.query(AuditEvent)
    if project_id:
        q = q.filter(AuditEvent.project_id == project_id)
    if entity_type:
        q = q.filter(AuditEvent.entity_type == entity_type)
    if entity_id:
        q = q.filter(AuditEvent.entity_id == entity_id)
    if action:
        q = q.filter(AuditEvent.action == action)
    if actor_id:
        q = q.filter(AuditEvent.actor_id == actor_id)
    events = q.order_by(AuditEvent.created_at.desc()).offset(skip).limit(limit).all()
    result = []
    for e in events:
        out = AuditEventOut(
            id=e.id,
            actor_id=e.actor_id,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            action=e.action,
            diff=json.loads(e.diff_json) if e.diff_json else None,
            reason=e.reason,
            source=e.source,
            project_id=e.project_id,
            created_at=e.created_at,
        )
        result.append(out)
    return result
