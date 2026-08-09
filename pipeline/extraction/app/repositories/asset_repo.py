"""Queries over `ExtractionAsset`, `AssetContextLink` and extraction `Job` records."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from shared.config import get_extraction_settings
from shared.db.models import AssetContextLink, DoclingCache, ExtractionAsset, Job

_settings = get_extraction_settings()

#: A job in one of these states is still doing work; starting a second one would race it.
ACTIVE_JOB_STATUSES = ("queued", "running")


def _filtered(
    query,
    asset_type: Optional[str],
    classification: Optional[str],
):
    if asset_type:
        query = query.filter(ExtractionAsset.asset_type == asset_type)
    if classification:
        query = query.filter(ExtractionAsset.classification == classification)
    return query


def page_for_paper(
    db: Session,
    paper_id: int,
    *,
    asset_type: Optional[str] = None,
    classification: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[int, list[ExtractionAsset]]:
    query = _filtered(
        db.query(ExtractionAsset).filter(ExtractionAsset.paper_id == paper_id),
        asset_type,
        classification,
    )
    total = query.count()
    assets = (
        query.order_by(ExtractionAsset.page_number, ExtractionAsset.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return total, assets


def page_for_project(
    db: Session,
    project_id: int,
    *,
    asset_type: Optional[str] = None,
    classification: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[int, list[ExtractionAsset]]:
    query = _filtered(
        db.query(ExtractionAsset).filter(ExtractionAsset.project_id == project_id),
        asset_type,
        classification,
    )
    total = query.count()
    assets = (
        query.order_by(
            ExtractionAsset.paper_id, ExtractionAsset.page_number, ExtractionAsset.id
        )
        .offset(skip)
        .limit(limit)
        .all()
    )
    return total, assets


def get(db: Session, paper_id: int, asset_id: int) -> ExtractionAsset | None:
    return (
        db.query(ExtractionAsset)
        .filter(ExtractionAsset.id == asset_id, ExtractionAsset.paper_id == paper_id)
        .first()
    )


def get_scoped(db: Session, project_id: int, paper_id: int, asset_id: int) -> ExtractionAsset | None:
    """Fetch with all three ids constrained -- used by the binary endpoints, where the
    signature was minted over exactly this triple."""
    return (
        db.query(ExtractionAsset)
        .filter(
            ExtractionAsset.id == asset_id,
            ExtractionAsset.paper_id == paper_id,
            ExtractionAsset.project_id == project_id,
        )
        .first()
    )


def all_for_paper_with_links(db: Session, paper_id: int) -> list[ExtractionAsset]:
    """Every asset for a paper with its context links eagerly loaded.

    `selectinload` matters here: evidence assembly walks `asset.context_links` for each of
    potentially hundreds of assets, which lazily would be one query per asset.
    """
    return (
        db.query(ExtractionAsset)
        .options(selectinload(ExtractionAsset.context_links))
        .filter(ExtractionAsset.paper_id == paper_id)
        .order_by(ExtractionAsset.relevance_score.desc(), ExtractionAsset.page_number)
        .all()
    )


def all_for_paper(db: Session, paper_id: int) -> list[ExtractionAsset]:
    """Every asset for a paper, without its links. Use when only the row is needed --
    stamping a gate verdict does not walk `context_links`, and eager-loading them is a
    second query per hundred assets for nothing."""
    return (
        db.query(ExtractionAsset)
        .filter(ExtractionAsset.paper_id == paper_id)
        .all()
    )


def count_for_paper(db: Session, paper_id: int) -> int:
    return db.query(ExtractionAsset).filter(ExtractionAsset.paper_id == paper_id).count()


def count_selected(db: Session, paper_id: int) -> int:
    return (
        db.query(ExtractionAsset)
        .filter(
            ExtractionAsset.paper_id == paper_id,
            ExtractionAsset.selected_for_llm.is_(True),
        )
        .count()
    )


def delete_for_paper(db: Session, paper_id: int) -> None:
    """Clear a paper's assets before a re-extraction writes fresh ones."""
    db.query(ExtractionAsset).filter(ExtractionAsset.paper_id == paper_id).delete(
        synchronize_session=False
    )


#: The only keys of a `build_context_links` dict that map to columns. Filtering here rather
#: than splatting blind means a linker that adds a transport-only key (a `same_page` flag, a
#: debug score) can no longer take down the whole extraction with a TypeError.
_LINK_FIELDS = frozenset({"link_type", "text", "item_ref", "page_number", "score"})


def set_silver_package(db: Session, file_hash: str, path: str) -> None:
    """Record where the gated package for this parse was staged.

    Keyed on the file hash, like the Docling cache it sits beside, so re-uploading the same
    paper into another project finds the work already done. Absent cache row is not an
    error: the ingestion job recomputes Silver from the cached parse.
    """
    cache = db.query(DoclingCache).filter(DoclingCache.file_hash == file_hash).first()
    if cache is not None:
        cache.silver_package_path = path


def silver_package_path(db: Session, file_hash: str) -> Optional[str]:
    cache = db.query(DoclingCache).filter(DoclingCache.file_hash == file_hash).first()
    return cache.silver_package_path if cache else None


def add_context_links(db: Session, asset_id: int, link_dicts: list[dict]) -> None:
    for link in link_dicts:
        db.add(
            AssetContextLink(
                asset_id=asset_id,
                **{key: value for key, value in link.items() if key in _LINK_FIELDS},
            )
        )


def active_job(db: Session, paper_id: int, job_type: str) -> Job | None:
    return (
        db.query(Job)
        .filter(
            Job.paper_id == paper_id,
            Job.job_type == job_type,
            Job.status.in_(ACTIVE_JOB_STATUSES),
        )
        .first()
    )


def latest_job(db: Session, paper_id: int, job_type: str) -> Job | None:
    return (
        db.query(Job)
        .filter(Job.paper_id == paper_id, Job.job_type == job_type)
        .order_by(Job.id.desc())
        .first()
    )


# ─── CSV shape helpers ────────────────────────────────────────────────────────
# Derived from the file rather than stored, because chart conversion can rewrite a CSV
# after the asset row is created.

def csv_dimensions(csv_path: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    """(rows, columns) for a generated CSV, or (None, None) if unreadable."""
    if not csv_path:
        return None, None
    path = Path(csv_path)
    if not path.exists():
        return None, None
    try:
        with path.open("r", encoding="utf-8") as handle:
            header = handle.readline()
            if not header:
                return 0, 0
            columns = len(header.split(","))
            rows = sum(1 for _ in handle)
        return rows, columns
    except OSError:
        return None, None
