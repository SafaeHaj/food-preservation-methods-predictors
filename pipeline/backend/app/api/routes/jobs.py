"""Job status polling and management."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.models import Job, User
from app.schemas.canonical import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
def list_jobs(
    project_id: Optional[int] = Query(None),
    paper_id: Optional[int] = Query(None),
    job_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Job)
    if project_id:
        q = q.filter(Job.project_id == project_id)
    if paper_id:
        q = q.filter(Job.paper_id == paper_id)
    if job_type:
        q = q.filter(Job.job_type == job_type)
    if status:
        q = q.filter(Job.status == status)
    return q.order_by(Job.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in ("completed", "failed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel job with status '{job.status}'")
    job.status = "cancelled"
    db.commit()
    db.refresh(job)
    return job
