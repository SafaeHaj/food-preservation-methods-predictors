"""Project team membership."""

from __future__ import annotations

from sqlalchemy.orm import Session

from shared.access import ROLES, authorize_project, get_membership
from shared.db.models import ProjectMember, User
from shared.errors import BusinessRuleError, ConflictError, NotFoundError, ValidationError
from shared.schemas.platform import ProjectMemberCreate, ProjectMemberUpdate
from shared.uow import unit_of_work


def _validate_role(role: str) -> None:
    if role not in ROLES:
        raise ValidationError(
            f"'{role}' is not a valid role", details={"allowed": sorted(ROLES)}
        )


def list_members(db: Session, project_id: int, user: User) -> list[ProjectMember]:
    authorize_project(db, project_id, user)
    return db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()


def add_member(
    db: Session, project_id: int, body: ProjectMemberCreate, user: User
) -> ProjectMember:
    authorize_project(db, project_id, user, "admin")
    _validate_role(body.role)

    invitee = db.query(User).filter(User.email == body.user_email).first()
    if not invitee:
        raise NotFoundError(
            "No user with that email address", details={"email": body.user_email}
        )
    if get_membership(db, project_id, invitee.id):
        raise ConflictError("That user is already a member of this project")

    member = ProjectMember(
        project_id=project_id, user_id=invitee.id, role=body.role, invited_by=user.id
    )
    with unit_of_work(db):
        db.add(member)
    db.refresh(member)
    return member


def update_member_role(
    db: Session, project_id: int, user_id: int, body: ProjectMemberUpdate, user: User
) -> ProjectMember:
    project = authorize_project(db, project_id, user, "admin")
    _validate_role(body.role)

    if project.owner_id == user_id and body.role != "owner":
        raise BusinessRuleError(
            "The project owner's role cannot be downgraded; transfer ownership instead"
        )

    member = get_membership(db, project_id, user_id)
    if not member:
        raise NotFoundError("That user is not a member of this project")

    with unit_of_work(db):
        member.role = body.role
    db.refresh(member)
    return member


def remove_member(db: Session, project_id: int, user_id: int, user: User) -> None:
    project = authorize_project(db, project_id, user, "admin")
    if project.owner_id == user_id:
        raise BusinessRuleError("The project owner cannot be removed from the project")

    member = get_membership(db, project_id, user_id)
    if not member:
        raise NotFoundError("That user is not a member of this project")

    with unit_of_work(db):
        db.delete(member)
