"""Project access policy -- the single definition of "may this user touch this project?".

Previously the predicate `Project.owner_id == user.id` was inlined at ~15 call sites, and
several routes (`/projects/{id}/assets`, `/projects/{id}/stats`, `/api/jobs/{id}`) simply
forgot it, which made them readable by any authenticated user. One definition, applied
through a dependency, is what stops that recurring.

Note the deliberate behaviour change: access is granted to the owner *or* any project
member. `ProjectMember` and the Team page already existed, but nothing consulted them --
inviting a collaborator granted them nothing.

Pure functions, no FastAPI: `shared.deps` wraps these as dependencies, and Celery tasks can
reuse them directly.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from shared.db.models import Job, Paper, Project, ProjectMember, User
from shared.errors import NotFoundError, PermissionDeniedError

#: Least to most privileged. A requirement of "reviewer" is satisfied by admin and owner.
ROLE_ORDER = ["viewer", "analyst", "reviewer", "admin", "owner"]
ROLES = set(ROLE_ORDER)


def role_satisfies(actual: str, required: str) -> bool:
    try:
        return ROLE_ORDER.index(actual) >= ROLE_ORDER.index(required)
    except ValueError:
        return False


def get_membership(db: Session, project_id: int, user_id: int) -> ProjectMember | None:
    return (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
        .first()
    )


def effective_role(db: Session, project: Project, user: User) -> str | None:
    """The caller's role on `project`, or None if they have no access.

    Ownership implies "owner" regardless of the membership table: projects created before
    owners were auto-enrolled have no `ProjectMember` row.
    """
    if project.owner_id == user.id:
        return "owner"
    membership = get_membership(db, project.id, user.id)
    return membership.role if membership else None


def authorize_project(
    db: Session, project_id: int, user: User, required_role: str = "viewer"
) -> Project:
    """Return the project if `user` may act on it at `required_role`, else raise.

    A project the caller cannot see is reported as 404, not 403: a 403 would confirm the
    project exists, letting an outsider enumerate ids.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundError.for_resource("Project", project_id)

    role = effective_role(db, project, user)
    if role is None:
        raise NotFoundError.for_resource("Project", project_id)
    if not role_satisfies(role, required_role):
        raise PermissionDeniedError(
            f"This action requires the '{required_role}' role or higher",
            details={"your_role": role, "required_role": required_role},
        )
    return project


def authorize_paper(db: Session, project_id: int, paper_id: int, user: User,
                    required_role: str = "viewer") -> Paper:
    """Authorize the project, then confirm the paper belongs to it."""
    authorize_project(db, project_id, user, required_role)
    paper = (
        db.query(Paper)
        .filter(Paper.id == paper_id, Paper.project_id == project_id)
        .first()
    )
    if not paper:
        raise NotFoundError.for_resource("Paper", paper_id)
    return paper


def authorize_job(db: Session, job_id: int, user: User, required_role: str = "viewer") -> Job:
    """Authorize a job through the project that owns it.

    Jobs are always reached this way; there is no such thing as a project-less job the
    caller may read. A job with no `project_id` is only visible to the user who created it.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise NotFoundError.for_resource("Job", job_id)

    if job.project_id is None:
        if job.created_by != user.id:
            raise NotFoundError.for_resource("Job", job_id)
        return job

    authorize_project(db, job.project_id, user, required_role)
    return job
