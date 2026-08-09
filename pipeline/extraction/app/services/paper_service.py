"""Paper upload, listing and deletion.

Owns the business rules (upload limits, file typing, storage layout) and the transaction.
The route below it only binds HTTP to these calls.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from shared.config import get_common_settings, get_extraction_settings
from shared.db.models import Paper
from shared.errors import BusinessRuleError, ValidationError
from shared.schemas.papers import PaperOut
from shared.uow import unit_of_work

from app.repositories import paper_repo

logger = logging.getLogger(__name__)

_settings = get_extraction_settings()
_common = get_common_settings()


class UploadedFile:
    """The parts of an `UploadFile` this service needs, already read into memory.

    Keeps the service free of FastAPI types so it stays unit-testable without a request.
    """

    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self.content = content


def _papers_dir(project_id: int) -> Path:
    directory = _common.storage_root / str(project_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _to_out(paper: Paper, counts: dict[str, int]) -> PaperOut:
    return PaperOut(
        id=paper.id,
        project_id=paper.project_id,
        filename=paper.filename,
        original_name=paper.original_name,
        page_count=paper.page_count,
        status=paper.status,
        error_message=paper.error_message,
        uploaded_at=paper.uploaded_at,
        asset_count=counts.get("asset_count", 0),
        experiment_count=counts.get("experiment_count", 0),
    )


def _serialize_many(db: Session, papers: list[Paper]) -> list[PaperOut]:
    counts = paper_repo.counts_by_paper(db, [p.id for p in papers])
    return [_to_out(paper, counts.get(paper.id, {})) for paper in papers]


def list_papers(db: Session, project_id: int) -> list[PaperOut]:
    return _serialize_many(db, paper_repo.list_for_project(db, project_id))


def get_paper(db: Session, paper: Paper) -> PaperOut:
    counts = paper_repo.counts_by_paper(db, [paper.id])
    return _to_out(paper, counts.get(paper.id, {}))


def upload_papers(db: Session, project_id: int, files: list[UploadedFile]) -> list[PaperOut]:
    """Validate, store and register a batch of PDFs."""
    if not files:
        raise ValidationError("No files were provided")
    if len(files) > _settings.MAX_PAPERS_PER_UPLOAD:
        raise BusinessRuleError(
            f"At most {_settings.MAX_PAPERS_PER_UPLOAD} files may be uploaded at once",
            details={"limit": _settings.MAX_PAPERS_PER_UPLOAD, "received": len(files)},
        )

    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            raise ValidationError(
                f"{file.filename} is not a PDF", details={"filename": file.filename}
            )
        if len(file.content) > _settings.max_upload_bytes:
            raise BusinessRuleError(
                f"{file.filename} exceeds the {_settings.MAX_UPLOAD_SIZE_MB} MB limit",
                details={"filename": file.filename, "limit_mb": _settings.MAX_UPLOAD_SIZE_MB},
            )

    directory = _papers_dir(project_id)
    created: list[Paper] = []

    # Files are written before the transaction commits. A crash in between leaves an
    # orphaned file, not an unreadable Paper row -- the safe direction of the two.
    with unit_of_work(db):
        for file in files:
            file_hash = hashlib.sha256(file.content).hexdigest()
            stored_name = f"{uuid.uuid4().hex[:12]}_{file.filename}"
            destination = directory / stored_name
            destination.write_bytes(file.content)

            created.append(
                paper_repo.add(
                    db,
                    Paper(
                        project_id=project_id,
                        filename=stored_name,
                        original_name=file.filename,
                        file_path=str(destination),
                        file_hash=file_hash,
                        # Filled by the workspace job from the Docling parse. Reading it at
                        # upload meant a second PDF library for one integer the parse then
                        # overwrote.
                        page_count=0,
                        status="uploaded",
                    ),
                )
            )

    return _serialize_many(db, created)


def delete_paper(db: Session, paper: Paper) -> None:
    """Remove the paper and its stored PDF. Cascades clear assets, runs and evidence."""
    file_path = Path(paper.file_path)
    with unit_of_work(db):
        paper_repo.delete(db, paper)

    # Only after the row is gone: a failed unlink must not leave a deleted row pointing at
    # a file, and an orphaned file is recoverable where a dangling row is not.
    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not delete stored file %s", file_path, exc_info=True)
