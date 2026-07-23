"""Observations CRUD + bulk create."""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.models import AuditEvent, Observation, TreatmentArm, User
from app.schemas.canonical import (
    ObservationBulkCreate, ObservationCreate, ObservationOut, ObservationUpdate,
)

router = APIRouter(prefix="/observations", tags=["observations"])


def _get_or_404(obs_id: int, db: Session) -> Observation:
    o = db.query(Observation).filter(Observation.id == obs_id).first()
    if not o:
        raise HTTPException(status_code=404, detail="Observation not found")
    return o


def _audit(db, user, eid, action, before=None, after=None):
    db.add(AuditEvent(
        actor_id=user.id, entity_type="observation", entity_id=eid, action=action,
        before_json=json.dumps(before) if before else None,
        after_json=json.dumps(after) if after else None,
        diff_json=json.dumps({}), source="user",
    ))


@router.get("", response_model=list[ObservationOut])
def list_observations(
    treatment_arm_id: Optional[int] = Query(None),
    experiment_id: Optional[int] = Query(None),
    project_id: Optional[int] = Query(None),
    measurement_type: Optional[str] = Query(None),
    review_status: Optional[str] = Query(None),
    include_imputed: bool = Query(True),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.db.models import Experiment, Study
    q = db.query(Observation)
    if treatment_arm_id:
        q = q.filter(Observation.treatment_arm_id == treatment_arm_id)
    elif experiment_id:
        q = q.join(TreatmentArm).filter(TreatmentArm.experiment_id == experiment_id)
    elif project_id:
        q = (q.join(TreatmentArm)
               .join(Experiment, TreatmentArm.experiment_id == Experiment.id)
               .join(Study, Experiment.study_id == Study.id)
               .filter(Study.project_id == project_id))
    if measurement_type:
        q = q.filter(Observation.measurement_type == measurement_type)
    if review_status:
        q = q.filter(Observation.review_status == review_status)
    if not include_imputed:
        q = q.filter(Observation.is_imputed == False)
    return q.order_by(Observation.time_days).offset(skip).limit(limit).all()


@router.post("", response_model=ObservationOut, status_code=status.HTTP_201_CREATED)
def create_observation(
    payload: ObservationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obs = Observation(**payload.model_dump(), created_by=current_user.id, updated_by=current_user.id)
    db.add(obs)
    db.flush()
    _audit(db, current_user, obs.id, "create", None, payload.model_dump())
    db.commit()
    db.refresh(obs)
    return obs


@router.post("/bulk", response_model=list[ObservationOut], status_code=status.HTTP_201_CREATED)
def bulk_create_observations(
    payload: ObservationBulkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    created = []
    for item in payload.observations:
        obs = Observation(**item.model_dump(), created_by=current_user.id, updated_by=current_user.id)
        db.add(obs)
        db.flush()
        _audit(db, current_user, obs.id, "create", None, item.model_dump())
        created.append(obs)
    db.commit()
    for obs in created:
        db.refresh(obs)
    return created


@router.get("/{obs_id}", response_model=ObservationOut)
def get_observation(
    obs_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_or_404(obs_id, db)


@router.patch("/{obs_id}", response_model=ObservationOut)
def update_observation(
    obs_id: int,
    payload: ObservationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obs = _get_or_404(obs_id, db)
    before = {"review_status": obs.review_status, "numeric_value_normalized": obs.numeric_value_normalized}
    data = payload.model_dump(exclude_none=True)
    for k, v in data.items():
        setattr(obs, k, v)
    obs.updated_by = current_user.id
    obs.version += 1
    db.flush()
    _audit(db, current_user, obs_id, "update", before, data)
    db.commit()
    db.refresh(obs)
    return obs


@router.post("/{obs_id}/approve", response_model=ObservationOut)
def approve_observation(
    obs_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obs = _get_or_404(obs_id, db)
    obs.review_status = "approved"
    obs.updated_by = current_user.id
    obs.version += 1
    db.flush()
    _audit(db, current_user, obs_id, "approve", None, {"review_status": "approved"})
    db.commit()
    db.refresh(obs)
    return obs


@router.delete("/{obs_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_observation(
    obs_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obs = _get_or_404(obs_id, db)
    _audit(db, current_user, obs_id, "delete",
           {"measurement_type": obs.measurement_type, "time_days": obs.time_days}, None)
    db.delete(obs)
    db.commit()
