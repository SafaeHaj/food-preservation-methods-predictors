"""Turning a paper's gated package into scientific records.

    POST /projects/{pid}/ingestion/papers/{paper_id}   start ingestion

Under `ingestion`, not `papers`, on purpose: the gateway routes on the third path segment
(`gateway/app/proxy.py::_target_for`), and `papers` already belongs to extraction. A URL
cannot be owned by two services, so the verb names the segment.

Progress is followed on `GET /api/jobs/{job_id}/events`, the same stream every other
long-running job uses; there is no status endpoint to poll.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from shared.db.database import get_db
from shared.db.models import DoclingCache, Job, Paper, Project, User
from shared.errors import BusinessRuleError, NotFoundError
from shared.uow import unit_of_work

from app.api.deps import get_current_user, require_project_contributor
from app.schemas.dataset import JobAccepted

router = APIRouter(tags=["ingestion"])

INGESTION_JOB = "paper_ingestion"
BATCH_JOB = "paper_batch_ingestion"


class BatchIngestionRequest(BaseModel):
    """Which papers to ingest. Empty means every one that has a package and no records yet,
    which is what "ingest the corpus" means in practice."""

    paper_ids: list[int] = Field(default_factory=list)
    #: Re-ingest papers already carrying experiments. Off by default: a re-run costs a model
    #: call per paper and overwrites rows that were probably fine.
    include_ingested: bool = False


@router.post("/projects/{project_id}/ingestion/batch", status_code=202,
             response_model=JobAccepted)
def ingest_batch(
    request: BatchIngestionRequest,
    project: Project = Depends(require_project_contributor),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Ingest many papers under one job, sequentially.

    Only papers with a staged package are eligible. Asking for one without is a mistake
    worth reporting: the fix is to run the workspace extraction, and silently skipping it
    would leave the user waiting for records that were never going to appear.
    """
    from app.tasks import run_batch_ingestion

    query = (
        db.query(Paper.id)
        .join(DoclingCache, DoclingCache.file_hash == Paper.file_hash)
        .filter(Paper.project_id == project.id,
                DoclingCache.silver_package_path.isnot(None))
    )
    if request.paper_ids:
        query = query.filter(Paper.id.in_(request.paper_ids))
    if not request.include_ingested:
        query = query.filter(Paper.status != "extracted")

    paper_ids = [row[0] for row in query.order_by(Paper.id).all()]
    if not paper_ids:
        raise BusinessRuleError(
            "No papers are ready to ingest. A paper needs a staged extraction package, "
            "and one already ingested needs include_ingested.",
            details={"project_id": project.id, "requested": request.paper_ids},
        )

    job = Job(
        project_id=project.id,
        job_type=BATCH_JOB,
        status="queued",
        current_step=f"Queued {len(paper_ids)} paper(s) for ingestion",
        progress=0,
        total_steps=len(paper_ids),
        created_by=user.id,
    )
    with unit_of_work(db):
        db.add(job)
    db.refresh(job)

    run_batch_ingestion.delay(paper_ids, project.id, job.id)
    return JobAccepted(job_id=job.id, status=job.status)


@router.post(
    "/projects/{project_id}/ingestion/papers/{paper_id}",
    status_code=202,
    response_model=JobAccepted,
)
def ingest_paper(
    paper_id: int,
    project: Project = Depends(require_project_contributor),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Read the gated package, resolve it against the vocabulary, and write the records.

    Re-entrant like every other start endpoint: a second click attaches to the run already
    in flight rather than queueing a duplicate pass over the same paper.
    """
    from app.tasks import run_paper_ingestion

    paper = (
        db.query(Paper)
        .filter(Paper.id == paper_id, Paper.project_id == project.id)
        .first()
    )
    if not paper:
        raise NotFoundError.for_resource("Paper", paper_id)

    running = (
        db.query(Job)
        .filter(
            Job.paper_id == paper.id,
            Job.job_type == INGESTION_JOB,
            Job.status.in_(("queued", "running")),
        )
        .order_by(Job.id.desc())
        .first()
    )
    if running:
        return JobAccepted(job_id=running.id, status=running.status)

    job = Job(
        project_id=project.id,
        paper_id=paper.id,
        job_type=INGESTION_JOB,
        status="queued",
        current_step="Queued for ingestion",
        progress=0,
        created_by=user.id,
    )
    with unit_of_work(db):
        db.add(job)
    db.refresh(job)

    run_paper_ingestion.delay(paper.id, project.id, job.id)
    return JobAccepted(job_id=job.id, status=job.status)
