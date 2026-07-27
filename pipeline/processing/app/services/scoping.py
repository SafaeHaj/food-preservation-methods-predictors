"""Resolve a canonical entity to its owning project, and authorize against it.

The canonical hierarchy is addressed by bare entity ids (`/observations/42`), so a route
handling one has no project id to check against -- which is why none of them checked
anything, and any authenticated user could read or edit any project's scientific data.

Each entity reaches its project by a fixed path:

    Study         -> project_id
    Experiment    -> study.project_id
    TreatmentArm  -> experiment.study.project_id
    Observation   -> treatment_arm.experiment.study.project_id
    everything else (Microorganism, NormalizationMapping, TrajectoryDefinition,
    ImputationProposal, ThresholdDefinition, DatasetSnapshot, ExportRun) -> project_id

A null `project_id` means a shared catalogue row (a globally-known microorganism, a
site-wide unit mapping): readable by anyone, editable by no one through these routes.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from shared.access import authorize_project
from shared.db.models import (
    Experiment, Observation, Study, TreatmentArm, User,
)
from shared.errors import NotFoundError, PermissionDeniedError


def project_id_of(entity) -> int | None:
    """The project that owns `entity`, or None for a shared catalogue row."""
    if isinstance(entity, Study):
        return entity.project_id
    if isinstance(entity, Experiment):
        return entity.study.project_id if entity.study else None
    if isinstance(entity, TreatmentArm):
        experiment = entity.experiment
        return experiment.study.project_id if experiment and experiment.study else None
    if isinstance(entity, Observation):
        arm = entity.treatment_arm
        experiment = arm.experiment if arm else None
        return experiment.study.project_id if experiment and experiment.study else None
    return getattr(entity, "project_id", None)


def authorize_entity(db: Session, entity, user: User, required_role: str = "viewer"):
    """Authorize `user` against the project owning `entity`, and return the entity.

    A shared row (no project) is readable by anyone but not writable: there is no project
    whose membership could grant the right to edit it.
    """
    project_id = project_id_of(entity)
    if project_id is None:
        if required_role != "viewer":
            raise PermissionDeniedError(
                "This is a shared catalogue entry and cannot be modified here"
            )
        return entity
    authorize_project(db, project_id, user, required_role)
    return entity


def require_entity(
    db: Session, model, entity_id: int, user: User, *,
    label: str, required_role: str = "viewer",
):
    """Fetch, authorize and return one entity, or raise `NotFoundError`."""
    entity = db.query(model).filter(model.id == entity_id).first()
    if not entity:
        raise NotFoundError.for_resource(label, entity_id)
    return authorize_entity(db, entity, user, required_role)


def scoped_project_ids(db: Session, user: User) -> list[int]:
    """Every project id the caller can see. Used to bound unfiltered list endpoints."""
    from shared.db.models import Project, ProjectMember

    owned = db.query(Project.id).filter(Project.owner_id == user.id)
    member = db.query(ProjectMember.project_id).filter(ProjectMember.user_id == user.id)
    return [row[0] for row in owned.union(member).all()]


def scope_query(
    db: Session, query, column, project_id: int | None, user: User,
    *, include_shared: bool = False,
):
    """Restrict a list query to what the caller may see.

    Every list endpoint took an *optional* `project_id` and, when it was omitted, returned
    the table -- every project's studies, thresholds, trajectories and imputations to any
    authenticated user. Omitting it now means "all of my projects", not "all projects".

    `include_shared` also admits rows with a null project (global catalogues such as the
    microorganism list and site-wide unit mappings).
    """
    if project_id is not None:
        authorize_project(db, project_id, user)
        condition = column == project_id
    else:
        condition = column.in_(scoped_project_ids(db, user))

    if include_shared:
        condition = condition | (column.is_(None))
    return query.filter(condition)
