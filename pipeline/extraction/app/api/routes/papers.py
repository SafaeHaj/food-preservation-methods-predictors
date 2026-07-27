"""Paper routes -- bind HTTP to `paper_service`, nothing more."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from shared.db.database import get_db
from shared.db.models import Paper, Project
from shared.schemas.papers import PaperOut

from app.api.deps import require_paper, require_paper_contributor, require_project, require_project_contributor
from app.services import paper_service

router = APIRouter(prefix="/projects/{project_id}/papers", tags=["papers"])


@router.get("", response_model=List[PaperOut])
def list_papers(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return paper_service.list_papers(db, project.id)


@router.get("/{paper_id}", response_model=PaperOut)
def get_paper(
    paper: Paper = Depends(require_paper),
    db: Session = Depends(get_db),
):
    return paper_service.get_paper(db, paper)


@router.post("", response_model=List[PaperOut], status_code=201)
async def upload_papers(
    files: List[UploadFile] = File(...),
    project: Project = Depends(require_project_contributor),
    db: Session = Depends(get_db),
):
    uploads = [
        paper_service.UploadedFile(file.filename or "unnamed.pdf", await file.read())
        for file in files
    ]
    return paper_service.upload_papers(db, project.id, uploads)


@router.delete("/{paper_id}", status_code=204)
def delete_paper(
    paper: Paper = Depends(require_paper_contributor),
    db: Session = Depends(get_db),
):
    paper_service.delete_paper(db, paper)
