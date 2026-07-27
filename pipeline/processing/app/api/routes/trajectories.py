"""Trajectory definitions + model fitting."""

import json
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from shared.auth import get_current_user
from shared.db.database import get_db
from shared.errors import BusinessRuleError
from shared.db.models import Observation, TrajectoryDefinition, User
from shared.schemas.canonical import TrajectoryCreate, TrajectoryOut, ModelRunOut

from app.services import scoping

router = APIRouter(prefix="/trajectories", tags=["trajectories"])


def _get_or_404(traj_id: int, db: Session, user: User, role: str = "viewer"):
    """Fetch and authorize through the project that owns it."""
    return scoping.require_entity(
        db, TrajectoryDefinition, traj_id, user, label="Trajectory", required_role=role
    )


@router.get("", response_model=list[TrajectoryOut])
def list_trajectories(
    project_id: Optional[int] = Query(None),
    experiment_id: Optional[int] = Query(None),
    treatment_arm_id: Optional[int] = Query(None),
    measurement_type: Optional[str] = Query(None),
    process_class: Optional[str] = Query(None),
    data_sufficient: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = scoping.scope_query(
        db, db.query(TrajectoryDefinition), TrajectoryDefinition.project_id,
        project_id, current_user,
    )
    if experiment_id:
        q = q.filter(TrajectoryDefinition.experiment_id == experiment_id)
    if treatment_arm_id:
        q = q.filter(TrajectoryDefinition.treatment_arm_id == treatment_arm_id)
    if measurement_type:
        q = q.filter(TrajectoryDefinition.measurement_type == measurement_type)
    if process_class:
        q = q.filter(TrajectoryDefinition.process_class == process_class)
    if data_sufficient is not None:
        q = q.filter(TrajectoryDefinition.data_sufficient == data_sufficient)
    return q.order_by(TrajectoryDefinition.id).offset(skip).limit(limit).all()


@router.post("", response_model=TrajectoryOut, status_code=status.HTTP_201_CREATED)
def create_trajectory(
    payload: TrajectoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Validate all observation_ids exist
    observations = []
    if payload.observation_ids:
        observations = (db.query(Observation)
                          .filter(Observation.id.in_(payload.observation_ids))
                          .all())
        if len(observations) != len(payload.observation_ids):
            raise BusinessRuleError("Some observation IDs not found")

    traj = TrajectoryDefinition(
        project_id=payload.project_id,
        experiment_id=payload.experiment_id,
        treatment_arm_id=payload.treatment_arm_id,
        label=payload.label,
        measurement_type=payload.measurement_type,
        measurement_subtype=payload.measurement_subtype,
        microorganism_id=payload.microorganism_id,
        n_points=len(payload.observation_ids),
        notes=payload.notes,
        created_by=current_user.id,
    )
    # Membership now lives in the trajectory_observations junction, not a JSON id list.
    traj.observations = observations
    db.add(traj)
    db.commit()
    db.refresh(traj)
    return traj


@router.get("/{traj_id}", response_model=TrajectoryOut)
def get_trajectory(
    traj_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_or_404(traj_id, db, current_user)


@router.delete("/{traj_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trajectory(
    traj_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    traj = _get_or_404(traj_id, db, current_user)
    db.delete(traj)
    db.commit()


@router.post("/{traj_id}/fit", response_model=ModelRunOut)
def fit_models(
    traj_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Launch model fitting for this trajectory."""
    traj = _get_or_404(traj_id, db, current_user)
    from shared.db.models import ModelRun
    run = ModelRun(
        trajectory_id=traj_id,
        project_id=traj.project_id,
        status="pending",
        created_by=current_user.id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    from app.tasks import run_trajectory_fit
    run_trajectory_fit.delay(run.id)
    return run


@router.get("/{traj_id}/runs", response_model=list[ModelRunOut])
def list_model_runs(
    traj_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_or_404(traj_id, db, current_user)
    from shared.db.models import ModelRun
    return (db.query(ModelRun)
              .filter(ModelRun.trajectory_id == traj_id)
              .order_by(ModelRun.created_at.desc())
              .all())
