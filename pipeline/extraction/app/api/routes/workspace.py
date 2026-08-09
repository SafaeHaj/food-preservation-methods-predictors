"""Extraction workspace routes.

    POST   /projects/{pid}/papers/{paper_id}/workspace          start the Docling pipeline
    GET    /projects/{pid}/papers/{paper_id}/assets             list assets
    GET    /projects/{pid}/papers/{paper_id}/assets/{id}        asset + context links
    PATCH  /projects/{pid}/papers/{paper_id}/assets/{id}        curate the LLM selection
    GET    /projects/{pid}/papers/{paper_id}/assets/{id}/image        signed binary
    GET    /projects/{pid}/papers/{paper_id}/assets/{id}/page-image   signed binary
    GET    /projects/{pid}/papers/{paper_id}/assets/{id}/csv          signed binary
    GET    /projects/{pid}/papers/{paper_id}/evidence-packages  LLM selection preview
    GET    /projects/{pid}/papers/{paper_id}/gate-report        schema-gate verdicts
    GET    /projects/{pid}/assets                               project-wide asset list

There is deliberately no `/workspace/status` or `/llm-job/{id}` endpoint: both start
endpoints return a `job_id`, and progress is followed on the one job resource at
`GET /api/jobs/{job_id}/events`.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from shared.db.database import get_db
from shared.db.models import Paper, Project, User

from app.api.deps import (
    get_current_user, require_paper, require_paper_contributor, require_project,
    verify_signed_asset,
)
from app.schemas.workspace import (
    AssetDetailOut, AssetPage, AssetUpdate, EvidencePackagesOut, GateReportOut, JobAccepted,
)
from app.services import workspace_service

router = APIRouter(tags=["extraction-workspace"])

#: Binaries are immutable once written -- a new parse creates new asset ids -- so they can
#: be cached hard. The signature's own expiry bounds how long the URL stays usable.
_ASSET_CACHE_HEADERS = {"Cache-Control": "private, max-age=3600"}


# ─── Jobs ─────────────────────────────────────────────────────────────────────

@router.post(
    "/projects/{project_id}/papers/{paper_id}/workspace",
    status_code=202,
    response_model=JobAccepted,
)
def start_workspace_extraction(
    paper: Paper = Depends(require_paper_contributor),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return workspace_service.start_extraction(db, paper, user.id)


# ─── Assets ───────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/papers/{paper_id}/assets", response_model=AssetPage)
def list_assets(
    asset_type: Optional[str] = Query(None),
    classification: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: Optional[int] = Query(None, ge=1),
    paper: Paper = Depends(require_paper),
    db: Session = Depends(get_db),
):
    return workspace_service.list_paper_assets(
        db, paper,
        asset_type=asset_type, classification=classification, skip=skip, limit=limit,
    )


@router.get("/projects/{project_id}/assets", response_model=AssetPage)
def list_project_assets(
    asset_type: Optional[str] = Query(None),
    classification: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: Optional[int] = Query(None, ge=1),
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return workspace_service.list_project_assets(
        db, project.id,
        asset_type=asset_type, classification=classification, skip=skip, limit=limit,
    )


@router.get(
    "/projects/{project_id}/papers/{paper_id}/assets/{asset_id}",
    response_model=AssetDetailOut,
)
def get_asset(
    asset_id: int,
    paper: Paper = Depends(require_paper),
    db: Session = Depends(get_db),
):
    return workspace_service.get_asset(db, paper, asset_id)


@router.patch(
    "/projects/{project_id}/papers/{paper_id}/assets/{asset_id}",
    response_model=AssetDetailOut,
)
def update_asset(
    asset_id: int,
    body: AssetUpdate,
    paper: Paper = Depends(require_paper_contributor),
    db: Session = Depends(get_db),
):
    return workspace_service.update_asset(db, paper, asset_id, body)


# ─── Binaries ─────────────────────────────────────────────────────────────────
# Authenticated by the URL signature rather than a bearer token: these are fetched by
# `<img src>` and `<a href>`, which cannot set headers. `verify_signed_asset` re-checks the
# signature here so the service is safe even if it were reachable without the gateway.

@router.get(
    "/projects/{project_id}/papers/{paper_id}/assets/{asset_id}/image",
    dependencies=[Depends(verify_signed_asset)],
)
def get_asset_image(
    project_id: int, paper_id: int, asset_id: int, db: Session = Depends(get_db)
):
    path = workspace_service.get_asset_file(db, project_id, paper_id, asset_id, "image")
    return FileResponse(str(path), media_type="image/png", headers=_ASSET_CACHE_HEADERS)


@router.get(
    "/projects/{project_id}/papers/{paper_id}/assets/{asset_id}/page-image",
    dependencies=[Depends(verify_signed_asset)],
)
def get_page_image(
    project_id: int, paper_id: int, asset_id: int, db: Session = Depends(get_db)
):
    path = workspace_service.get_asset_file(db, project_id, paper_id, asset_id, "page-image")
    return FileResponse(str(path), media_type="image/png", headers=_ASSET_CACHE_HEADERS)


@router.get(
    "/projects/{project_id}/papers/{paper_id}/assets/{asset_id}/csv",
    dependencies=[Depends(verify_signed_asset)],
)
def get_asset_csv(
    project_id: int, paper_id: int, asset_id: int, db: Session = Depends(get_db)
):
    path = workspace_service.get_asset_file(db, project_id, paper_id, asset_id, "csv")
    return FileResponse(
        str(path),
        media_type="text/csv",
        filename=f"asset_{asset_id}.csv",
        headers=_ASSET_CACHE_HEADERS,
    )


# ─── Evidence preview ─────────────────────────────────────────────────────────

@router.get(
    "/projects/{project_id}/papers/{paper_id}/evidence-packages",
    response_model=EvidencePackagesOut,
)
def get_evidence_packages(
    paper: Paper = Depends(require_paper),
    db: Session = Depends(get_db),
):
    return workspace_service.evidence_packages(db, paper)


@router.get(
    "/projects/{project_id}/papers/{paper_id}/gate-report",
    response_model=GateReportOut,
)
def get_gate_report(
    paper: Paper = Depends(require_paper),
    db: Session = Depends(get_db),
):
    """What the schema gate decided about every table and figure, and why.

    Distinct from `/evidence-packages`, which reports the curation policy — which assets a
    human selected or the relevance score auto-included. This reports the structural
    verdict: whether the asset holds an ordered series the pipeline can actually read. The
    first answers "what will be sent", the second "what could be extracted", and a paper
    that produces less than expected is usually explained by the second.
    """
    return workspace_service.gate_report(db, paper)
