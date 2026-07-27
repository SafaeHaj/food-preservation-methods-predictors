"""Extraction workspace: starting jobs, reading assets, curating the LLM selection."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from shared.config import get_common_settings, get_extraction_settings, get_gateway_settings
from shared.db.models import ExtractionAsset, Job, Paper
from shared.errors import BusinessRuleError, NotFoundError
from shared.signing import sign_path
from shared.uow import unit_of_work

from app.repositories import asset_repo
from app.schemas.workspace import (
    AssetDetailOut, AssetLinks, AssetOut, AssetPage, AssetUpdate, ContextLinkOut,
    EvidenceAssetOut, EvidencePackagesOut, EvidenceTotals, JobAccepted, ParagraphOut,
)
from app.services import asset_selection

logger = logging.getLogger(__name__)

_common = get_common_settings()
_settings = get_extraction_settings()
_gateway = get_gateway_settings()

WORKSPACE_JOB = "workspace_extraction"
LLM_JOB = "llm_validation"

#: Longest context snippet echoed back to the Validation page. The full text is available
#: on the asset detail endpoint; the list view only needs enough to recognise it.
PARAGRAPH_PREVIEW_CHARS = 600
LINK_PREVIEW_CHARS = 500


# ─── Serialization ────────────────────────────────────────────────────────────

def _exists(path: Optional[str]) -> bool:
    return bool(path and Path(path).exists())


def _asset_links(asset: ExtractionAsset) -> AssetLinks:
    """Signed, expiring URLs for the asset's binaries.

    Minted here, on an authenticated read, which is what lets the gateway stop treating
    every `/image` and `/csv` path as public.
    """
    base = f"/api/projects/{asset.project_id}/papers/{asset.paper_id}/assets/{asset.id}"
    ttl = _gateway.ASSET_URL_TTL_SECONDS
    secret = _common.SECRET_KEY

    return AssetLinks(
        image=sign_path(secret, f"{base}/image", ttl) if _exists(asset.image_path) else None,
        page_image=(
            sign_path(secret, f"{base}/page-image", ttl) if _exists(asset.page_image_path) else None
        ),
        csv=sign_path(secret, f"{base}/csv", ttl) if _exists(asset.csv_path) else None,
    )


def _bbox(asset: ExtractionAsset) -> Optional[dict]:
    if not asset.bbox_json:
        return None
    try:
        return json.loads(asset.bbox_json)
    except json.JSONDecodeError:
        logger.warning("Asset %s has an unparseable bbox", asset.id)
        return None


def _base_fields(asset: ExtractionAsset, paper_name: Optional[str] = None) -> dict:
    links = _asset_links(asset)
    return {
        "id": asset.id,
        "paper_id": asset.paper_id,
        "project_id": asset.project_id,
        "docling_item_ref": asset.docling_item_ref,
        "asset_type": asset.asset_type,
        "page_number": asset.page_number,
        "bbox": _bbox(asset),
        "section_name": asset.section_name,
        "caption": asset.caption,
        "classification": asset.classification,
        "conversion_status": asset.conversion_status,
        "conversion_error": asset.conversion_error,
        "relevance_score": asset.relevance_score or 0.0,
        "selected_for_llm": bool(asset.selected_for_llm),
        "user_note": asset.user_note,
        "csv_rows": asset.csv_rows,
        "csv_cols": asset.csv_cols,
        "has_image": links.image is not None,
        "has_page_image": links.page_image is not None,
        "has_csv": links.csv is not None,
        "links": links,
        "paper_name": paper_name,
        "created_at": asset.created_at,
    }


def to_out(asset: ExtractionAsset, paper_name: Optional[str] = None) -> AssetOut:
    return AssetOut(**_base_fields(asset, paper_name))


def to_detail(asset: ExtractionAsset) -> AssetDetailOut:
    return AssetDetailOut(
        **_base_fields(asset),
        context_links=[
            ContextLinkOut.model_validate(link)
            for link in sorted(asset.context_links, key=lambda item: -(item.score or 0))
        ],
    )


# ─── Reads ────────────────────────────────────────────────────────────────────

def _clamp(limit: int) -> int:
    return max(1, min(limit, _settings.MAX_ASSET_PAGE_SIZE))


def list_paper_assets(
    db: Session, paper: Paper, *, asset_type: Optional[str] = None,
    classification: Optional[str] = None, skip: int = 0, limit: int | None = None,
) -> AssetPage:
    total, assets = asset_repo.page_for_paper(
        db, paper.id,
        asset_type=asset_type, classification=classification,
        skip=skip, limit=_clamp(limit or _settings.DEFAULT_ASSET_PAGE_SIZE),
    )
    return AssetPage(total=total, items=[to_out(asset) for asset in assets])


def list_project_assets(
    db: Session, project_id: int, *, asset_type: Optional[str] = None,
    classification: Optional[str] = None, skip: int = 0, limit: int | None = None,
) -> AssetPage:
    total, assets = asset_repo.page_for_project(
        db, project_id,
        asset_type=asset_type, classification=classification,
        skip=skip, limit=_clamp(limit or _settings.DEFAULT_ASSET_PAGE_SIZE),
    )

    paper_ids = {asset.paper_id for asset in assets}
    names = (
        dict(db.query(Paper.id, Paper.original_name).filter(Paper.id.in_(paper_ids)).all())
        if paper_ids
        else {}
    )
    return AssetPage(
        total=total,
        items=[to_out(asset, names.get(asset.paper_id)) for asset in assets],
    )


def get_asset(db: Session, paper: Paper, asset_id: int) -> AssetDetailOut:
    asset = asset_repo.get(db, paper.id, asset_id)
    if not asset:
        raise NotFoundError.for_resource("Asset", asset_id)
    return to_detail(asset)


def get_asset_file(
    db: Session, project_id: int, paper_id: int, asset_id: int, kind: str
) -> Path:
    """Resolve one of an asset's binaries to an on-disk path.

    `kind` is "image" | "page-image" | "csv". Raises `NotFoundError` when the asset has no
    such file or the file has gone missing, which are the same thing from the caller's side.
    """
    asset = asset_repo.get_scoped(db, project_id, paper_id, asset_id)
    if not asset:
        raise NotFoundError.for_resource("Asset", asset_id)

    stored = {
        "image": asset.image_path,
        "page-image": asset.page_image_path,
        "csv": asset.csv_path,
    }.get(kind)

    if not _exists(stored):
        raise NotFoundError(f"This asset has no {kind}", details={"asset_id": asset_id})
    return Path(stored)


# ─── Writes ───────────────────────────────────────────────────────────────────

def update_asset(db: Session, paper: Paper, asset_id: int, body: AssetUpdate) -> AssetDetailOut:
    asset = asset_repo.get(db, paper.id, asset_id)
    if not asset:
        raise NotFoundError.for_resource("Asset", asset_id)

    with unit_of_work(db):
        # exclude_unset, not exclude_none: clearing a note to null is a real edit that a
        # None-based check would silently drop.
        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(asset, field, value)

    return to_detail(asset)


def _start_job(db: Session, paper: Paper, user_id: int, job_type: str, step: str) -> Job:
    """Create a queued job, or return the one already running.

    Re-entrancy matters: the workspace page starts extraction on mount, and a refresh
    mid-run must attach to the existing job rather than parse the PDF a second time.
    """
    running = asset_repo.active_job(db, paper.id, job_type)
    if running:
        return running

    job = Job(
        project_id=paper.project_id,
        paper_id=paper.id,
        job_type=job_type,
        status="queued",
        current_step=step,
        progress=0,
        created_by=user_id,
    )
    with unit_of_work(db):
        db.add(job)
    db.refresh(job)
    return job


def start_extraction(db: Session, paper: Paper, user_id: int) -> JobAccepted:
    """Queue the Docling workspace pipeline for one paper."""
    from app.tasks import run_workspace_extraction

    job = _start_job(db, paper, user_id, WORKSPACE_JOB, "Queued for extraction")
    if job.status == "queued":
        run_workspace_extraction.delay(paper.id, paper.project_id, job.id)
    return JobAccepted(job_id=job.id, status=job.status)


def send_to_llm(db: Session, paper: Paper, user_id: int) -> JobAccepted:
    """Queue LLM ingestion over the curated asset selection."""
    from app.tasks import run_llm_ingestion

    if asset_repo.count_for_paper(db, paper.id) == 0:
        raise BusinessRuleError(
            "This paper has no extracted assets yet; run the extraction pipeline first",
            details={"paper_id": paper.id},
        )

    job = _start_job(db, paper, user_id, LLM_JOB, "Queued for LLM extraction")
    if job.status == "queued":
        run_llm_ingestion.delay(paper.id, paper.project_id, job.id)
    return JobAccepted(job_id=job.id, status=job.status)


# ─── Evidence preview ─────────────────────────────────────────────────────────

def evidence_packages(db: Session, paper: Paper) -> EvidencePackagesOut:
    """What would be sent to the LLM, and why.

    Uses the same `asset_selection` policy the ingestion job uses, so this preview cannot
    disagree with what actually happens -- which it previously could, being a second
    hand-written copy of the rules.
    """
    from app.services.chart_converter import _chart_model_error

    assets = asset_repo.all_for_paper_with_links(db, paper.id)

    paragraphs: list[ParagraphOut] = []
    native_tables: list[EvidenceAssetOut] = []
    chart_csvs: list[EvidenceAssetOut] = []
    excluded: list[EvidenceAssetOut] = []

    for asset in assets:
        verdict = asset_selection.judge(asset)
        links = sorted(asset.context_links, key=lambda item: -(item.score or 0))

        entry = EvidenceAssetOut(
            **_base_fields(asset),
            context_links=[
                ContextLinkOut(
                    id=link.id,
                    link_type=link.link_type,
                    text=link.text[:LINK_PREVIEW_CHARS],
                    item_ref=link.item_ref,
                    page_number=link.page_number,
                    score=link.score or 0.0,
                )
                for link in links
            ],
            link_count=len(links),
            auto_include=verdict.auto_include,
            auto_reason=verdict.auto_reason,
            is_decorative=verdict.is_decorative,
            effective_include=verdict.include,
            exclude_reason=verdict.exclude_reason,
        )

        if not verdict.include:
            excluded.append(entry)
        elif asset.asset_type == "native_table":
            native_tables.append(entry)
        elif asset.classification == "chart" and asset.csv_path:
            chart_csvs.append(entry)
        else:
            paragraphs.extend(
                ParagraphOut(
                    asset_id=asset.id,
                    link_id=link.id,
                    link_type=link.link_type,
                    text=link.text[:PARAGRAPH_PREVIEW_CHARS],
                    page_number=link.page_number or asset.page_number,
                    score=link.score or 0.0,
                    section_name=asset.section_name,
                    asset_caption=asset.caption,
                    relevance_score=asset.relevance_score or 0.0,
                    auto_reason=verdict.auto_reason,
                )
                for link in links
                if link.link_type in asset_selection.TEXT_LINK_TYPES
            )

    return EvidencePackagesOut(
        paragraphs=paragraphs,
        native_tables=native_tables,
        chart_csvs=chart_csvs,
        excluded=excluded,
        totals=EvidenceTotals(
            paragraphs=len(paragraphs),
            native_tables=len(native_tables),
            chart_csvs=len(chart_csvs),
            excluded=len(excluded),
        ),
        chart_conversion_available=_chart_model_error is None,
        chart_conversion_error=_chart_model_error,
    )
