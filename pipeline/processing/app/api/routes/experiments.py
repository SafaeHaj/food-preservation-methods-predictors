"""Experiments CRUD + microorganism assignments."""

import json
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from shared.auth import get_current_user
from shared.db.database import get_db
from shared.errors import NotFoundError
from shared.db.models import AuditEvent, Experiment, ExperimentMicroorganism, User
from shared.schemas.canonical import (
    ExperimentCreate, ExperimentDetail, ExperimentOut, ExperimentUpdate,
    ExperimentMicroorganismCreate, ExperimentMicroorganismOut,
    TreatmentArmBrief,
)

from app.services import scoping

router = APIRouter(prefix="/experiments", tags=["experiments"])


def _get_or_404(experiment_id: int, db: Session, user: User, role: str = "viewer"):
    """Fetch and authorize through the project that owns it."""
    return scoping.require_entity(
        db, Experiment, experiment_id, user, label="Experiment", required_role=role
    )


def _audit(db, user, eid, action, before=None, after=None, reason=None):
    diff = {}
    if before and after:
        diff = {k: {"before": before.get(k), "after": after.get(k)}
                for k in set(list(before) + list(after)) if before.get(k) != after.get(k)}
    db.add(AuditEvent(
        actor_id=user.id, entity_type="experiment", entity_id=eid, action=action,
        before_json=json.dumps(before) if before else None,
        after_json=json.dumps(after) if after else None,
        diff_json=json.dumps(diff), reason=reason, source="user",
    ))


@router.get("", response_model=list[ExperimentOut])
def list_experiments(
    study_id: Optional[int] = Query(None),
    project_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Experiments reach their project through Study, so the scope is applied on the join
    # rather than on the row -- and it is applied whether or not project_id was supplied.
    from shared.db.models import Study

    q = scoping.scope_query(
        db, db.query(Experiment).join(Study, Study.id == Experiment.study_id),
        Study.project_id, project_id, current_user,
    )
    if study_id:
        q = q.filter(Experiment.study_id == study_id)
    return q.order_by(Experiment.created_at).offset(skip).limit(limit).all()


@router.post("", response_model=ExperimentOut, status_code=status.HTTP_201_CREATED)
def create_experiment(
    payload: ExperimentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = payload.model_dump(exclude={"gas_composition", "extra_conditions"})
    exp = Experiment(
        **data,
        gas_composition_json=json.dumps(payload.gas_composition),
        extra_conditions_json=json.dumps(payload.extra_conditions),
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(exp)
    db.flush()
    _audit(db, current_user, exp.id, "create", None, payload.model_dump())
    db.commit()
    db.refresh(exp)
    return exp


@router.get("/{experiment_id}", response_model=ExperimentDetail)
def get_experiment(
    experiment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_or_404(experiment_id, db, current_user)


@router.patch("/{experiment_id}", response_model=ExperimentOut)
def update_experiment(
    experiment_id: int,
    payload: ExperimentUpdate,
    reason: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = _get_or_404(experiment_id, db, current_user)
    data = payload.model_dump(exclude_none=True)
    if "gas_composition" in data:
        exp.gas_composition_json = json.dumps(data.pop("gas_composition"))
    if "extra_conditions" in data:
        exp.extra_conditions_json = json.dumps(data.pop("extra_conditions"))
    for k, v in data.items():
        setattr(exp, k, v)
    exp.updated_by = current_user.id
    exp.version += 1
    db.flush()
    _audit(db, current_user, experiment_id, "update", None, data, reason)
    db.commit()
    db.refresh(exp)
    return exp


@router.delete("/{experiment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_experiment(
    experiment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = _get_or_404(experiment_id, db, current_user)
    _audit(db, current_user, experiment_id, "delete", {"product": exp.product_name_normalized}, None)
    db.delete(exp)
    db.commit()


# ── Microorganism assignments ──────────────────────────────────────────────

@router.post("/{experiment_id}/microorganisms",
             response_model=ExperimentMicroorganismOut,
             status_code=status.HTTP_201_CREATED)
def assign_microorganism(
    experiment_id: int,
    payload: ExperimentMicroorganismCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_or_404(experiment_id, db, current_user)
    link = ExperimentMicroorganism(
        experiment_id=experiment_id,
        microorganism_id=payload.microorganism_id,
        role_in_study=payload.role_in_study,
        inoculum_level=payload.inoculum_level,
        inoculum_unit=payload.inoculum_unit,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@router.delete("/{experiment_id}/microorganisms/{micro_id}",
               status_code=status.HTTP_204_NO_CONTENT)
def remove_microorganism(
    experiment_id: int,
    micro_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    link = (db.query(ExperimentMicroorganism)
            .filter_by(experiment_id=experiment_id, microorganism_id=micro_id)
            .first())
    if not link:
        raise NotFoundError("Assignment not found")
    db.delete(link)
    db.commit()
