"""LLM ingestion: curated assets -> structured experiments -> canonical hierarchy.

This is the single ingestion path. It replaces two near-identical implementations (the
workspace's `_run_llm_validation` and `food_extraction`'s `_run_food_extraction`) and adds
the step neither of them had: promoting the result into the canonical
Study/Experiment/TreatmentArm/Observation hierarchy. Previously that promotion only ran
from the legacy flat-row path, behind a manual "promote" button, so the scientific database
pages stayed empty no matter how many papers were extracted here.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from shared.config import get_extraction_settings
from shared.db.models import Job, Paper
from shared.services.canonical_promoter import promote_paper_to_canonical
from shared.uow import JobProgressReporter

from app.repositories import asset_repo
from app.services import asset_selection, evidence_writer, ext_writer
from app.services.evidence_builder import build_packages
from app.services.food_extractor import extract_food_data

logger = logging.getLogger(__name__)
_settings = get_extraction_settings()

PROGRESS_SELECT = 10
PROGRESS_PACKAGES = 25
PROGRESS_LLM = 40
PROGRESS_PERSIST = 80
PROGRESS_PROMOTE = 92


def run(db: Session, paper: Paper, job_id: int, progress: JobProgressReporter) -> dict:
    """Extract structured data for one paper. Returns the job result payload.

    Runs inside the caller's transaction, so the `ext_*` writes and the canonical promotion
    commit together: the scientific database can never show half of a paper.
    """
    progress.update(progress=PROGRESS_SELECT, step="Selecting evidence assets")
    assets = asset_repo.all_for_paper_with_links(db, paper.id)
    selected = asset_selection.select_for_llm(assets)

    progress.update(
        progress=PROGRESS_PACKAGES,
        step=f"Building evidence packages from {len(selected)} assets",
    )
    packages, known_refs = build_packages(selected)

    if not packages:
        logger.info("Paper %s produced no evidence packages", paper.id)
        return {
            "experiments": 0,
            "measurements": 0,
            "reasoning": "No relevant evidence was found in the selected assets.",
            "low_confidence_count": 0,
            "_step": "Done — no relevant evidence found",
        }

    progress.update(
        progress=PROGRESS_LLM, step=f"Sending {len(packages)} package(s) for extraction"
    )
    result = extract_food_data(
        evidence_packages=packages,
        known_item_refs=known_refs,
        enable_verification=_settings.LLM_ENABLE_VERIFICATION,
    )
    experiments = result.get("experiments", [])

    progress.update(
        progress=PROGRESS_PERSIST, step=f"Saving {len(experiments)} experiment(s)"
    )
    written = ext_writer.write_experiments(
        db,
        project_id=paper.project_id,
        paper_id=paper.id,
        job_id=job_id,
        experiments=experiments,
        evidence_sink=evidence_writer.make_sink(
            db, paper.id, paper.file_path, evidence_writer.build_reference_index(assets)
        ),
    )

    # Promotion is part of ingestion, not a separate user action. It is idempotent, so a
    # re-extraction updates the canonical hierarchy rather than duplicating it.
    progress.update(progress=PROGRESS_PROMOTE, step="Promoting to the scientific database")
    promoted = promote_paper_to_canonical(paper.id, paper.project_id, db)

    return {
        **written.as_dict(),
        "reasoning": result.get("reasoning_summary", ""),
        "low_confidence_count": result.get("low_confidence_count", 0),
        "promoted": promoted,
        "_step": (
            f"Done — {written.experiments} experiments, {written.measurements} measurements, "
            f"{promoted['observations']} observations"
        ),
    }
