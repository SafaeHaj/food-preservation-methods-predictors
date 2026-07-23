import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db, SessionLocal
from app.db.models import ExtractedRow, Job, Paper, Project, User
from app.schemas.papers import RowOut
from app.services.ai_extractor import extract_data_with_ai, split_row_and_provenance
from app.services.pdf_extractor import extract_full_text
from app.services.validator import validate_row

router = APIRouter(prefix="/projects/{project_id}/extract", tags=["extraction"])


def _run_extraction(paper_id: int, project_id: int, job_id: Optional[int] = None):
    db = SessionLocal()
    try:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        project = db.query(Project).filter(Project.id == project_id).first()
        if not paper or not project:
            return

        paper.status = "extracting"
        if job_id:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = "running"
                job.started_at = datetime.utcnow()
                job.current_step = "Extracting text from PDF"
        db.commit()

        schema_fields = project.schema

        full_text, page_count = extract_full_text(paper.file_path)
        paper.page_count = page_count

        if job_id:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.progress = 40
                job.current_step = "Running AI extraction"
                db.commit()

        raw_rows = extract_data_with_ai(full_text, schema_fields)
        # Guard: AI extractor can return None on provider failure; treat as empty list.
        if raw_rows is None:
            raw_rows = []
        if not isinstance(raw_rows, list):
            logger.error("extract_data_with_ai returned unexpected type %s; treating as empty", type(raw_rows))
            raw_rows = []

        for raw_row in raw_rows:
            data, prov = split_row_and_provenance(raw_row)
            is_valid, violations = validate_row(data, schema_fields)
            note = "; ".join(violations) if violations else ""
            db.add(ExtractedRow(
                paper_id=paper.id,
                project_id=project_id,
                data_json=json.dumps(data),
                provenance_json=json.dumps(prov),
                status="pending",
                reviewer_note=note,
            ))

        paper.status = "extracted"
        if job_id:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.progress = 80
                job.current_step = "Promoting to canonical data model"
                db.commit()

        from app.services.canonical_promoter import promote_paper_to_canonical
        promotion = promote_paper_to_canonical(paper_id, project_id, db)

        if job_id:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = "completed"
                job.progress = 100
                job.current_step = f"Done — {len(raw_rows)} rows, {promotion.get('observations', 0)} observations"
                job.completed_at = datetime.utcnow()
                job.result_json = json.dumps({"rows_extracted": len(raw_rows), **promotion})
        db.commit()

    except Exception as e:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if paper:
            paper.status = "error"
            paper.error_message = str(e)[:500]
        if job_id:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = "failed"
                job.error_message = str(e)[:500]
                job.completed_at = datetime.utcnow()
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

    job = Job(
        project_id=project_id,
        paper_id=paper.id,
        job_type="extraction",
        status="queued",
        created_by=user.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(_run_extraction, paper.id, project_id, job.id)
    return {"message": "Extraction started", "paper_id": paper_id, "job_id": job.id}


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
    job_ids = []
    for paper in papers:
        job = Job(
            project_id=project_id,
            paper_id=paper.id,
            job_type="extraction",
            status="queued",
            created_by=user.id,
        )
        db.add(job)
        db.flush()
        background_tasks.add_task(_run_extraction, paper.id, project_id, job.id)
        job_ids.append(job.id)
    db.commit()
    return {"message": f"Extraction started for {len(papers)} papers", "job_ids": job_ids}
