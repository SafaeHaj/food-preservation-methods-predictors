"""Treatment arms CRUD."""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.models import AuditEvent, TreatmentArm, User
from app.schemas.canonical import TreatmentArmCreate, TreatmentArmOut, TreatmentArmUpdate

router = APIRouter(prefix="/treatment-arms", tags=["treatment_arms"])


def _get_or_404(arm_id: int, db: Session) -> TreatmentArm:
    a = db.query(TreatmentArm).filter(TreatmentArm.id == arm_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Treatment arm not found")
    return a


@router.get("", response_model=list[TreatmentArmOut])
def list_arms(
    experiment_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(TreatmentArm)
    if experiment_id:
        q = q.filter(TreatmentArm.experiment_id == experiment_id)
    return q.order_by(TreatmentArm.id).offset(skip).limit(limit).all()


@router.post("", response_model=TreatmentArmOut, status_code=status.HTTP_201_CREATED)
def create_arm(
    payload: TreatmentArmCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = payload.model_dump(exclude={"combination_treatments", "extra_treatment"})
    arm = TreatmentArm(
        **data,
        combination_treatments_json=json.dumps(payload.combination_treatments),
        extra_treatment_json=json.dumps(payload.extra_treatment),
        created_by=current_user.id,
    )
    db.add(arm)
    db.flush()
    db.add(AuditEvent(actor_id=current_user.id, entity_type="treatment_arm",
                      entity_id=arm.id, action="create", source="user",
                      after_json=json.dumps(payload.model_dump())))
    db.commit()
    db.refresh(arm)
    return arm


@router.get("/{arm_id}", response_model=TreatmentArmOut)
def get_arm(
    arm_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_or_404(arm_id, db)


@router.patch("/{arm_id}", response_model=TreatmentArmOut)
def update_arm(
    arm_id: int,
    payload: TreatmentArmUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    arm = _get_or_404(arm_id, db)
    data = payload.model_dump(exclude_none=True)
    if "combination_treatments" in data:
        arm.combination_treatments_json = json.dumps(data.pop("combination_treatments"))
    if "extra_treatment" in data:
        arm.extra_treatment_json = json.dumps(data.pop("extra_treatment"))
    for k, v in data.items():
        setattr(arm, k, v)
    arm.version += 1
    db.flush()
    db.add(AuditEvent(actor_id=current_user.id, entity_type="treatment_arm",
                      entity_id=arm_id, action="update", source="user",
                      after_json=json.dumps(data)))
    db.commit()
    db.refresh(arm)
    return arm


@router.delete("/{arm_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_arm(
    arm_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    arm = _get_or_404(arm_id, db)
    db.add(AuditEvent(actor_id=current_user.id, entity_type="treatment_arm",
                      entity_id=arm_id, action="delete", source="user"))
    db.delete(arm)
    db.commit()
