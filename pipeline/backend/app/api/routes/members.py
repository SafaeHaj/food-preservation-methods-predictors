"""Project team member management."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.models import Project, ProjectMember, User
from app.schemas.canonical import (
    ProjectMemberCreate, ProjectMemberOut, ProjectMemberUpdate,
)

router = APIRouter(prefix="/projects/{project_id}/members", tags=["members"])

ROLES = {"owner", "admin", "reviewer", "analyst", "viewer"}


def _get_project_or_404(project_id: int, db: Session) -> Project:
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


def _get_membership(project_id: int, user_id: int, db: Session) -> ProjectMember | None:
    return (db.query(ProjectMember)
              .filter_by(project_id=project_id, user_id=user_id)
              .first())


def _require_admin(project_id: int, current_user: User, db: Session):
    membership = _get_membership(project_id, current_user.id, db)
    project = _get_project_or_404(project_id, db)
    if project.owner_id == current_user.id:
        return
    if not membership or membership.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Admin or owner role required")


@router.get("", response_model=list[ProjectMemberOut])
def list_members(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_project_or_404(project_id, db)
    return (db.query(ProjectMember)
              .filter(ProjectMember.project_id == project_id)
              .all())


@router.post("", response_model=ProjectMemberOut, status_code=status.HTTP_201_CREATED)
def add_member(
    project_id: int,
    payload: ProjectMemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(project_id, current_user, db)
    if payload.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Choose from {ROLES}")

    user = db.query(User).filter(User.email == payload.user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    existing = _get_membership(project_id, user.id, db)
    if existing:
        raise HTTPException(status_code=409, detail="User is already a member")

    member = ProjectMember(
        project_id=project_id,
        user_id=user.id,
        role=payload.role,
        invited_by=current_user.id,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


@router.patch("/{user_id}", response_model=ProjectMemberOut)
def update_member_role(
    project_id: int,
    user_id: int,
    payload: ProjectMemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(project_id, current_user, db)
    if payload.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Choose from {ROLES}")
    member = _get_membership(project_id, user_id, db)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    member.role = payload.role
    db.commit()
    db.refresh(member)
    return member


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    project_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(project_id, current_user, db)
    project = _get_project_or_404(project_id, db)
    if project.owner_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot remove the project owner")
    member = _get_membership(project_id, user_id, db)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    db.delete(member)
    db.commit()
