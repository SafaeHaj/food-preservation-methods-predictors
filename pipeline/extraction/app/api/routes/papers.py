import os
import shutil
import uuid
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings, UPLOAD_PATH
from app.db.database import get_db
from app.db.models import ExtractedRow, Paper, Project, User
from app.schemas.papers import PaperOut
from app.services.pdf_extractor import extract_full_text

router = APIRouter(prefix="/projects/{project_id}/papers", tags=["papers"])


def _paper_out(paper: Paper, db: Session) -> PaperOut:
    row_count = db.query(ExtractedRow).filter(ExtractedRow.paper_id == paper.id).count()
    return PaperOut(
        id=paper.id,
        project_id=paper.project_id,
        filename=paper.filename,
        original_name=paper.original_name,
        page_count=paper.page_count,
        status=paper.status,
        error_message=paper.error_message,
        uploaded_at=paper.uploaded_at,
        row_count=row_count,
    )


def _get_project(project_id: int, user: User, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == user.id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.get("", response_model=List[PaperOut])
def list_papers(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_project(project_id, user, db)
    papers = db.query(Paper).filter(Paper.project_id == project_id).order_by(Paper.uploaded_at.desc()).all()
    return [_paper_out(p, db) for p in papers]


@router.post("", response_model=List[PaperOut], status_code=201)
async def upload_papers(
    project_id: int,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_project(project_id, user, db)

    if len(files) > settings.MAX_PAPERS_PER_UPLOAD:
        raise HTTPException(400, f"Max {settings.MAX_PAPERS_PER_UPLOAD} files per upload")

    project_dir = UPLOAD_PATH / str(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)

    created = []
    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, f"{file.filename} is not a PDF")

        uid = uuid.uuid4().hex[:12]
        stored_name = f"{uid}_{file.filename}"
        dest = project_dir / stored_name

        content = await file.read()
        if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise HTTPException(413, f"{file.filename} exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit")

        with open(dest, "wb") as f:
            f.write(content)

        # Try to get page count
        page_count = 0
        try:
            _, page_count = extract_full_text(str(dest))
        except Exception:
            pass

        paper = Paper(
            project_id=project_id,
            filename=stored_name,
            original_name=file.filename,
            file_path=str(dest),
            page_count=page_count,
            status="uploaded",
        )
        db.add(paper)
        db.flush()
        created.append(_paper_out(paper, db))

    db.commit()
    return created


@router.delete("/{paper_id}", status_code=204)
def delete_paper(
    project_id: int,
    paper_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_project(project_id, user, db)
    paper = db.query(Paper).filter(Paper.id == paper_id, Paper.project_id == project_id).first()
    if not paper:
        raise HTTPException(404, "Paper not found")
    if os.path.exists(paper.file_path):
        os.remove(paper.file_path)
    db.delete(paper)
    db.commit()
