"""FastAPI dependencies built on the `shared.access` policy.

The gateway and the domain services authenticate differently -- the gateway verifies the
JWT, the domain services trust the gateway's `X-User-Id` header -- so the dependencies are
produced by a factory bound to whichever `get_current_user` the service uses. The policy
itself is shared; only the two-line binding differs.

Usage, once per service::

    project_deps = make_project_dependencies(get_current_user)
    RequireProject = project_deps.require_project

    @router.get("/projects/{project_id}/assets")
    def list_assets(project: Project = Depends(RequireProject)):
        ...

The route no longer takes `project_id`, `db` and `user` just to re-run the same query: it
receives the authorized `Project`. Forgetting the check stops being possible, because there
is nothing left to forget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import Depends
from sqlalchemy.orm import Session

from shared.access import authorize_job, authorize_paper, authorize_project
from shared.db.database import get_db
from shared.db.models import Job, Paper, Project, User


@dataclass(frozen=True)
class ProjectDependencies:
    """Ready-to-use dependencies, plus factories for role-gated variants."""

    require_project: Callable[..., Project]
    require_paper: Callable[..., Paper]
    require_job: Callable[..., Job]
    #: `require_project_role("admin")` -> a dependency enforcing at least that role.
    require_project_role: Callable[[str], Callable[..., Project]]
    require_paper_role: Callable[[str], Callable[..., Paper]]


def make_project_dependencies(get_current_user: Callable[..., User]) -> ProjectDependencies:
    """Bind the access policy to a service's authentication dependency."""

    def require_project_role(required_role: str) -> Callable[..., Project]:
        def dependency(
            project_id: int,
            db: Session = Depends(get_db),
            user: User = Depends(get_current_user),
        ) -> Project:
            return authorize_project(db, project_id, user, required_role)

        return dependency

    def require_paper_role(required_role: str) -> Callable[..., Paper]:
        def dependency(
            project_id: int,
            paper_id: int,
            db: Session = Depends(get_db),
            user: User = Depends(get_current_user),
        ) -> Paper:
            return authorize_paper(db, project_id, paper_id, user, required_role)

        return dependency

    def require_job(
        job_id: int,
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user),
    ) -> Job:
        return authorize_job(db, job_id, user)

    return ProjectDependencies(
        require_project=require_project_role("viewer"),
        require_paper=require_paper_role("viewer"),
        require_job=require_job,
        require_project_role=require_project_role,
        require_paper_role=require_paper_role,
    )
