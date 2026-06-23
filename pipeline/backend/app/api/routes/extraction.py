import json
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db, SessionLocal
from app.db.models import ExtractedRow, Paper, Project, User
from app.schemas.papers import RowOut
from app.services.ai_extractor import extract_data_with_ai, split_row_and_provenance
from app.services.pdf_extractor import extract_full_text
from app.services.validator import validate_row

router = APIRouter(prefix="/projects/{project_id}/extract", tags=["extraction"])


def _run_extraction(paper_id: int, project_id: int):
    db = SessionLocal()
    try:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        project = db.query(Project).filter(Project.id == project_id).first()
        if not paper or not project:
            return

        paper.status = "extracting"
        db.commit()

        schema_fields = project.schema

        # Extract text
        full_text, page_count = extract_full_text(paper.file_path)
        paper.page_count = page_count

        # AI extraction
        raw_rows = extract_data_with_ai(full_text, schema_fields)

        for raw_row in raw_rows:
            data, prov = split_row_and_provenance(raw_row)
            is_valid, violations = validate_row(data, schema_fields)
            note = "; ".join(violations) if violations else ""
            row = ExtractedRow(
                paper_id=paper.id,
                project_id=project_id,
                data_json=json.dumps(data),
                provenance_json=json.dumps(prov),
                status="pending",
                reviewer_note=note,
            )
            db.add(row)

        paper.status = "extracted"
        db.commit()

    except Exception as e:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if paper:
            paper.status = "error"
            paper.error_message = str(e)[:500]
            db.commit()
    finally:
        db.close()


@router.post("/{paper_id}", status_code=202)
def trigger_extraction(
    project_id: int,
    paper_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == user.id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    paper = db.query(Paper).filter(Paper.id == paper_id, Paper.project_id == project_id).first()
    if not paper:
        raise HTTPException(404, "Paper not found")
    if paper.status == "extracting":
        raise HTTPException(409, "Extraction already in progress")

    background_tasks.add_task(_run_extraction, paper.id, project_id)
    return {"message": "Extraction started", "paper_id": paper_id}


@router.post("", status_code=202)
def trigger_all_extraction(
    project_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == user.id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    papers = db.query(Paper).filter(
        Paper.project_id == project_id,
        Paper.status.in_(["uploaded", "error"]),
    ).all()
    for paper in papers:
        background_tasks.add_task(_run_extraction, paper.id, project_id)
    return {"message": f"Extraction started for {len(papers)} papers"}
