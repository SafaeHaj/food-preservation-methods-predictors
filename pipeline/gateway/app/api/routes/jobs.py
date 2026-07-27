"""Job routes -- the one async-work resource every workflow reports through."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from shared.db.database import get_db
from shared.db.models import User
from shared.schemas.canonical import JobOut

from app.api.deps import get_current_user
from app.services import job_service

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
    user: User = Depends(get_current_user),
):
    return job_service.list_jobs(
        db, user,
        project_id=project_id, paper_id=paper_id, job_type=job_type,
        status=status, skip=skip, limit=limit,
    )


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return job_service.get_job(db, job_id, user)


@router.get("/{job_id}/events")
def stream_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Server-Sent Events for one job's progress.

    Authorized once here, on the request session; the stream then re-checks per tick with
    its own session, so revoking access mid-run closes the stream rather than leaking on.
    """
    job_service.get_job(db, job_id, user)
    return StreamingResponse(
        job_service.stream_job_events(job_id, user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # nginx buffers proxied responses by default, which would hold every frame
            # until the stream closed and defeat the point of streaming.
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return job_service.cancel_job(db, job_id, user)
