"""Reading the gated package extraction staged for one paper.

The consumer half of the contract in `shared.schemas.silver`. Extraction writes the file to
the shared uploads volume and records its path on `DoclingCache.silver_package_path`; this
resolves that pointer, validates the payload, and hands processing a typed package.

It deliberately cannot recompute. The previous version of this code called `extract_pdf` to
recover a file hash it already had on the `Paper` row, which would have dragged Docling and
PaddleOCR into this service's image for nothing. A missing package is an instruction to
re-run the workspace job, not a reason to parse a PDF here.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from shared.db.models import Paper
from shared.errors import BusinessRuleError
from shared.schemas.silver import PACKAGE_VERSION, SilverPackage

from app.repositories import package_repo

logger = logging.getLogger(__name__)

_RERUN = "Run the workspace extraction for this paper first"


def load(db: Session, paper: Paper) -> dict:
    """The paper's gated package, validated. Raises `BusinessRuleError` when there is none.

    Returns the plain dict rather than the model: every stage downstream mutates the package
    in place -- `review` promotes assets between its lists, `normalise` attaches a reading --
    and a frozen model would mean converting back and forth at each step. Validation happens
    here, once, which is what the contract is for.
    """
    if not paper.file_hash:
        raise BusinessRuleError(
            f"Paper {paper.id} has no file hash, so no extraction has run. {_RERUN}",
            details={"paper_id": paper.id},
        )

    path = package_repo.silver_package_path(db, paper.file_hash)
    if not path or not Path(path).exists():
        raise BusinessRuleError(
            f"No gated package is staged for paper {paper.id}. {_RERUN}",
            details={"paper_id": paper.id, "expected_path": path},
        )

    try:
        package = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BusinessRuleError(
            f"The gated package for paper {paper.id} is unreadable. {_RERUN}",
            details={"paper_id": paper.id, "path": path, "reason": str(exc)},
        ) from exc

    version = package.get("package_version")
    if version != PACKAGE_VERSION:
        # A version mismatch means the two services were deployed apart. Say so, rather
        # than failing three modules deep in normalisation on a field that moved.
        raise BusinessRuleError(
            f"The gated package for paper {paper.id} is version {version!r}, but this "
            f"service reads {PACKAGE_VERSION!r}. {_RERUN}",
            details={"paper_id": paper.id, "found": version, "expected": PACKAGE_VERSION},
        )

    SilverPackage.model_validate(package)
    logger.info("Loaded the gated package for paper %s (%s observations)",
                paper.id, (package.get("gate_report") or {}).get("observations", 0))
    return package
