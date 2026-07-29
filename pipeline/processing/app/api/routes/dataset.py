"""Dataset routes — the project's scientific tables, flattened for modelling.

    GET  /projects/{pid}/dataset          the built dataset, or why there isn't one
    POST /projects/{pid}/dataset/build    queue a build; returns a job to follow

Progress is followed on `GET /api/jobs/{job_id}/events`, the same stream the extraction
workflows use. There is no `/dataset/status` to poll.

The builder itself is not written yet (see `services/dataset_builder`), so a build reports
what it would have consumed and writes nothing. The route is real regardless: the job
lifecycle, the authorization and the response shape are the parts that would otherwise be
rewritten three times as the builder took shape.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.db.database import get_db
from shared.db.models import Job, Project, User

from app.api.deps import get_current_user, require_project, require_project_contributor
from app.schemas.dataset import DatasetPreview, JobAccepted
from app.services import dataset_builder

router = APIRouter(tags=["dataset"])

DATASET_JOB = "dataset_build"


@router.get("/projects/{project_id}/dataset", response_model=DatasetPreview)
def get_dataset(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return dataset_builder.preview(db, project.id)


@router.post("/projects/{project_id}/dataset/build", status_code=202, response_model=JobAccepted)
def build_dataset(
    project: Project = Depends(require_project_contributor),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.tasks import run_dataset_build
    from shared.uow import unit_of_work

    # Re-entrant, like the extraction starts: a second click attaches to the build already
    # running rather than queueing a duplicate pass over the same tables.
    running = (
        db.query(Job)
        .filter(
            Job.project_id == project.id,
            Job.job_type == DATASET_JOB,
            Job.status.in_(("queued", "running")),
        )
        .order_by(Job.id.desc())
        .first()
    )
    if running:
        return JobAccepted(job_id=running.id, status=running.status)

    job = Job(
        project_id=project.id,
        job_type=DATASET_JOB,
        status="queued",
        current_step="Queued for dataset build",
        progress=0,
        created_by=user.id,
    )
    with unit_of_work(db):
        db.add(job)
    db.refresh(job)

    run_dataset_build.delay(project.id, job.id)
    return JobAccepted(job_id=job.id, status=job.status)
