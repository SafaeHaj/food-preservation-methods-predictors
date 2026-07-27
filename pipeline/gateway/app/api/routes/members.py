"""Team membership routes -- bind HTTP to `member_service`, nothing more."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from shared.db.database import get_db
from shared.db.models import User
from shared.schemas.canonical import (
    ProjectMemberCreate, ProjectMemberOut, ProjectMemberUpdate,
)

from app.api.deps import get_current_user
from app.services import member_service

router = APIRouter(prefix="/projects/{project_id}/members", tags=["members"])


@router.get("", response_model=list[ProjectMemberOut])
def list_members(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return member_service.list_members(db, project_id, user)


@router.post("", response_model=ProjectMemberOut, status_code=status.HTTP_201_CREATED)
def add_member(
    project_id: int,
    payload: ProjectMemberCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return member_service.add_member(db, project_id, payload, user)


@router.patch("/{user_id}", response_model=ProjectMemberOut)
def update_member_role(
    project_id: int,
    user_id: int,
    payload: ProjectMemberUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return member_service.update_member_role(db, project_id, user_id, payload, user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    project_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    member_service.remove_member(db, project_id, user_id, user)
