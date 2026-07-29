"""Project lifecycle and statistics.

Extracted from the route module, which previously held the default schema as 22 lines of
literals, ran a synchronous promotion loop over every paper in the project, and computed
statistics by materializing every entity id into Python lists.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from shared.access import authorize_project, effective_role
from shared.db.models import (
    Experiment, ExtractionRun, Indicator, Ingredient, Measurement, Paper, Project,
    ProjectMember, User,
)
from shared.schemas.projects import ProjectCreate, ProjectOut, ProjectStats, ProjectUpdate
from shared.uow import unit_of_work

from app.config import load_default_schema

logger = logging.getLogger(__name__)


def _to_out(db: Session, project: Project, user: User) -> ProjectOut:
    paper_count = db.query(func.count(Paper.id)).filter(Paper.project_id == project.id).scalar() or 0
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        schema_fields=project.schema,
        created_at=project.created_at,
        updated_at=project.updated_at,
        owner_id=project.owner_id,
        paper_count=paper_count,
        your_role=effective_role(db, project, user) or "viewer",
    )


def list_projects(db: Session, user: User) -> list[ProjectOut]:
    """Projects the caller owns or is a member of.

    Membership was previously ignored here, so an invited collaborator saw an empty
    dashboard even though the Team page listed them.
    """
    member_project_ids = (
        db.query(ProjectMember.project_id)
        .filter(ProjectMember.user_id == user.id)
        .scalar_subquery()
    )
    projects = (
        db.query(Project)
        .filter((Project.owner_id == user.id) | (Project.id.in_(member_project_ids)))
        .order_by(Project.created_at.desc())
        .all()
    )
    return [_to_out(db, project, user) for project in projects]


def get_project(db: Session, project_id: int, user: User) -> ProjectOut:
    return _to_out(db, authorize_project(db, project_id, user), user)


def create_project(db: Session, body: ProjectCreate, user: User) -> ProjectOut:
    schema = body.schema_fields or load_default_schema()
    with unit_of_work(db):
        project = Project(
            name=body.name,
            description=body.description,
            schema_json=json.dumps([field.model_dump() for field in schema]),
            owner_id=user.id,
        )
        db.add(project)
        db.flush()
        # Enrol the owner so the Team page and the membership-based access check agree.
        db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
    db.refresh(project)
    return _to_out(db, project, user)


def update_project(db: Session, project_id: int, body: ProjectUpdate, user: User) -> ProjectOut:
    project = authorize_project(db, project_id, user, "admin")
    with unit_of_work(db):
        if body.name is not None:
            project.name = body.name
        if body.description is not None:
            project.description = body.description
        if body.schema_fields is not None:
            project.schema_json = json.dumps([f.model_dump() for f in body.schema_fields])
    db.refresh(project)
    return _to_out(db, project, user)


def delete_project(db: Session, project_id: int, user: User) -> None:
    project = authorize_project(db, project_id, user, "owner")
    with unit_of_work(db):
        db.delete(project)


def get_stats(db: Session, project_id: int, user: User) -> ProjectStats:
    """Overview aggregates, as grouped counts rather than id materializations.

    An earlier implementation loaded every study id, then every experiment id, then every
    arm id into Python lists to build `IN (...)` clauses -- unbounded memory and query size
    that grew with the project. Every table here carries `project_id` directly, so the joins
    that made that tempting are gone too; only measurements need one, through their
    experiment.
    """
    authorize_project(db, project_id, user)

    def count(model, *where) -> int:
        return db.query(func.count()).select_from(model).filter(*where).scalar() or 0

    measurement_count = (
        db.query(func.count())
        .select_from(Measurement)
        .join(Experiment, Experiment.id == Measurement.experiment_id)
        .filter(Experiment.project_id == project_id)
        .scalar()
        or 0
    )

    last_run = (
        db.query(func.max(ExtractionRun.created_at))
        .join(Paper, Paper.id == ExtractionRun.paper_id)
        .filter(Paper.project_id == project_id)
        .scalar()
    )

    return ProjectStats(
        paper_count=count(Paper, Paper.project_id == project_id),
        experiment_count=count(Experiment, Experiment.project_id == project_id),
        measurement_count=measurement_count,
        ingredient_count=count(Ingredient, Ingredient.project_id == project_id),
        indicator_count=count(Indicator, Indicator.project_id == project_id),
        indicators_with_threshold=count(
            Indicator,
            Indicator.project_id == project_id,
            Indicator.indicator_threshold.isnot(None),
        ),
        member_count=count(ProjectMember, ProjectMember.project_id == project_id),
        last_extraction_at=last_run.isoformat() if last_run else None,
    )
