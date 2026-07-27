"""Project routes -- bind HTTP to `project_service`, nothing more."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.db.database import get_db
from shared.db.models import User
from shared.schemas.projects import ProjectCreate, ProjectOut, ProjectStats, ProjectUpdate

from app.api.deps import get_current_user
from app.services import project_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=List[ProjectOut])
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return project_service.list_projects(db, user)


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return project_service.create_project(db, body, user)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return project_service.get_project(db, project_id, user)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    body: ProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return project_service.update_project(db, project_id, body, user)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project_service.delete_project(db, project_id, user)


@router.get("/{project_id}/stats", response_model=ProjectStats)
def get_project_stats(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return project_service.get_stats(db, project_id, user)
