"""Queries over `Paper` and its per-paper counts."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from shared.db.models import Experiment, ExtractionAsset, Paper


def list_for_project(db: Session, project_id: int) -> list[Paper]:
    return (
        db.query(Paper)
        .filter(Paper.project_id == project_id)
        .order_by(Paper.uploaded_at.desc())
        .all()
    )


def add(db: Session, paper: Paper) -> Paper:
    db.add(paper)
    db.flush()
    return paper


def delete(db: Session, paper: Paper) -> None:
    db.delete(paper)


def find_by_hash(db: Session, project_id: int, file_hash: str) -> Paper | None:
    return (
        db.query(Paper)
        .filter(Paper.project_id == project_id, Paper.file_hash == file_hash)
        .first()
    )


def counts_by_paper(db: Session, paper_ids: list[int]) -> dict[int, dict[str, int]]:
    """Asset and experiment counts for many papers in two queries.

    Batched deliberately: the previous per-paper `.count()` inside the serializer meant
    listing 40 papers issued 40 extra queries.
    """
    if not paper_ids:
        return {}

    counts: dict[int, dict[str, int]] = {
        paper_id: {"asset_count": 0, "experiment_count": 0} for paper_id in paper_ids
    }

    asset_rows = (
        db.query(ExtractionAsset.paper_id, func.count(ExtractionAsset.id))
        .filter(ExtractionAsset.paper_id.in_(paper_ids))
        .group_by(ExtractionAsset.paper_id)
        .all()
    )
    for paper_id, count in asset_rows:
        counts[paper_id]["asset_count"] = count

    experiment_rows = (
        db.query(Experiment.paper_id, func.count(Experiment.id))
        .filter(Experiment.paper_id.in_(paper_ids))
        .group_by(Experiment.paper_id)
        .all()
    )
    for paper_id, count in experiment_rows:
        counts[paper_id]["experiment_count"] = count

    return counts
