"""Job querying, cancellation and progress streaming.

`Job` is the single async-work resource. Every long-running operation in every service --
Docling extraction, LLM ingestion, model training, exports -- reports through it, so the
frontend needs exactly one way to follow progress instead of a bespoke status endpoint per
workflow.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator, Optional

from sqlalchemy.orm import Session

from shared.access import authorize_job, authorize_project
from shared.config import get_gateway_settings
from shared.db.database import SessionLocal
from shared.db.models import Job, ProjectMember, User
from shared.errors import BusinessRuleError
from shared.schemas.canonical import JobOut
from shared.uow import unit_of_work

logger = logging.getLogger(__name__)

_settings = get_gateway_settings()

#: A job in one of these states will never change again, so a stream can close.
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "partial_success"})


def list_jobs(
    db: Session,
    user: User,
    *,
    project_id: Optional[int] = None,
    paper_id: Optional[int] = None,
    job_type: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Job]:
    """Jobs visible to the caller.

    Previously unscoped: any authenticated user could list and read every job in the
    installation, including other tenants' error messages and result payloads.
    """
    query = db.query(Job)

    if project_id is not None:
        authorize_project(db, project_id, user)
        query = query.filter(Job.project_id == project_id)
    else:
        # No explicit project: restrict to projects the caller can actually see.
        visible = (
            db.query(ProjectMember.project_id)
            .filter(ProjectMember.user_id == user.id)
            .scalar_subquery()
        )
        query = query.filter(
            Job.project_id.in_(visible)
            | ((Job.project_id.is_(None)) & (Job.created_by == user.id))
        )

    if paper_id is not None:
        query = query.filter(Job.paper_id == paper_id)
    if job_type:
        query = query.filter(Job.job_type == job_type)
    if status:
        query = query.filter(Job.status == status)

    return query.order_by(Job.created_at.desc()).offset(skip).limit(limit).all()


def get_job(db: Session, job_id: int, user: User) -> Job:
    return authorize_job(db, job_id, user)


def cancel_job(db: Session, job_id: int, user: User) -> Job:
    job = authorize_job(db, job_id, user, "analyst")
    if job.status in TERMINAL_STATUSES:
        raise BusinessRuleError(
            f"A job that has already {job.status} cannot be cancelled",
            details={"job_id": job_id, "status": job.status},
        )
    with unit_of_work(db):
        job.status = "cancelled"
    db.refresh(job)
    return job


def _snapshot(job: Job) -> dict:
    """The progress facts a client needs. Deliberately narrower than `JobOut`."""
    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress or 0,
        "current_step": job.current_step or "",
        "error": job.error_message or None,
        "result": job.result or None,
    }


async def stream_job_events(job_id: int, user_id: int) -> AsyncIterator[str]:
    """Server-Sent Events for one job, until it reaches a terminal state.

    Replaces the per-workflow polling loops. Each connection opens its own short-lived
    session per tick rather than holding one for the lifetime of the stream, which could be
    an hour: a pooled connection parked on an idle stream is a connection no request can use.

    Frames are only emitted when something actually changed, so an extraction that sits at
    35% for two minutes sends one frame, not a hundred.
    """
    loop = asyncio.get_running_loop()
    last_payload: str | None = None
    elapsed = 0.0
    since_keepalive = 0.0

    def read_snapshot() -> dict | None:
        db = SessionLocal()
        try:
            from shared.db.models import User as UserModel

            user = db.query(UserModel).filter(UserModel.id == user_id).first()
            if not user:
                return None
            return _snapshot(authorize_job(db, job_id, user))
        finally:
            db.close()

    while elapsed < _settings.JOB_STREAM_MAX_SECONDS:
        # The ORM read is blocking; keep it off the event loop so one slow query cannot
        # stall every other connection this worker is serving.
        try:
            snapshot = await loop.run_in_executor(None, read_snapshot)
        except Exception:
            logger.exception("Job stream %s failed to read state", job_id)
            yield _frame("error", {"message": "Could not read job state"})
            return

        if snapshot is None:
            yield _frame("error", {"message": "Job is no longer accessible"})
            return

        payload = json.dumps(snapshot, default=str)
        if payload != last_payload:
            last_payload = payload
            since_keepalive = 0.0
            yield f"event: progress\ndata: {payload}\n\n"

        if snapshot["status"] in TERMINAL_STATUSES:
            yield _frame("done", snapshot)
            return

        await asyncio.sleep(_settings.JOB_STREAM_POLL_SECONDS)
        elapsed += _settings.JOB_STREAM_POLL_SECONDS
        since_keepalive += _settings.JOB_STREAM_POLL_SECONDS

        # Comment frame: keeps intermediaries from reaping a stream that is legitimately
        # quiet during a long pipeline stage.
        if since_keepalive >= _settings.JOB_STREAM_KEEPALIVE_SECONDS:
            since_keepalive = 0.0
            yield ": keepalive\n\n"

    yield _frame("error", {"message": "Job stream timed out; poll /api/jobs/{id} instead"})


def _frame(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def to_out(job: Job) -> JobOut:
    return JobOut.model_validate(job)
