"""Registering packages extracted elsewhere, so ingestion can read them.

The workspace job normally writes both halves of the handover: the package file, and the
`Paper` + `DoclingCache` rows that point at it. An extraction run on the HPC box writes only
the first half -- a directory per paper, with `gate.json` in it and no database in sight.

This closes that gap and does nothing else. It creates the rows the pointer needs and
validates the package against the same contract `package_reader` enforces, so a malformed
directory fails here, naming the paper, rather than inside a Celery worker on paper forty.

It deliberately does not ingest. Registration is idempotent and cheap; ingestion costs a
model call per paper. Keeping them apart means re-importing a corpus after adding papers
does not re-run the expensive half, and `--dry-run` can report exactly what would change.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from shared.db.models import DoclingCache, Paper
from shared.schemas.silver import PACKAGE_VERSION, SilverPackage

logger = logging.getLogger(__name__)

PACKAGE_FILENAME = "gate.json"

#: Set on a registered paper. `uploaded` would claim a PDF is on the uploads volume, which
#: for an imported package is not true -- there is a parse, and no file behind it.
IMPORTED_STATUS = "extracted"


@dataclass
class ImportResult:
    registered: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    failed: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"registered": self.registered, "updated": self.updated,
                "skipped": self.skipped, "failed": self.failed}


def discover(root: Path) -> list[Path]:
    """Every directory under `root` holding a package. Sorted, so a run is reproducible.

    Directories starting with `_` are the extraction run's own bookkeeping (`_logs`,
    `_prefetch`), not papers.
    """
    return sorted(
        path.parent for path in root.glob(f"*/{PACKAGE_FILENAME}")
        if not path.parent.name.startswith("_")
    )


def read_package(directory: Path) -> tuple[dict, bool]:
    """The directory's package, validated against the shared contract. (package, stamped).

    `package_version` is supplied when absent rather than rejected: a package written
    before the field existed is structurally the current one, and the validation below is
    what actually decides that, not a string comparison.

    `stamped` says the field had to be added. It matters because `package_reader` reads
    this file from disk and refuses an unknown version -- so a package normalised only in
    memory would import cleanly and then fail at ingestion, which is exactly the kind of
    lie this contract exists to prevent.
    """
    payload = json.loads((directory / PACKAGE_FILENAME).read_text(encoding="utf-8"))
    stamped = payload.get("package_version") != PACKAGE_VERSION
    payload["package_version"] = PACKAGE_VERSION
    payload.setdefault("source_name", f"{directory.name}.pdf")
    SilverPackage.model_validate(payload)
    return payload, stamped


def _stamp(directory: Path, package: dict) -> None:
    """Write the validated version back, so the file on disk is what the reader accepts.

    Written via a temporary file and replaced atomically: a process killed mid-write must
    not leave a truncated package where a valid one was.
    """
    target = directory / PACKAGE_FILENAME
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    temporary.replace(target)


def _paper_for(db: Session, project_id: int, package: dict, directory: Path) -> tuple:
    """This package's paper row, by file hash within the project. (paper, created)."""
    file_hash = package["file_hash"]
    paper = (
        db.query(Paper)
        .filter(Paper.project_id == project_id, Paper.file_hash == file_hash)
        .first()
    )
    if paper:
        return paper, False

    paper = Paper(
        project_id=project_id,
        filename=directory.name,
        original_name=package.get("source_name") or directory.name,
        # No PDF was uploaded: the parse is the artefact. The column is NOT NULL, so it
        # points at what does exist -- the directory the package came out of.
        file_path=str(directory),
        file_hash=file_hash,
        page_count=package.get("page_count", 0),
        status=IMPORTED_STATUS,
    )
    db.add(paper)
    db.flush()
    return paper, True


def _cache_for(db: Session, paper: Paper, package: dict, directory: Path) -> None:
    """The pointer `package_reader` resolves. Keyed on the hash, like the parse it stands for."""
    cache = (
        db.query(DoclingCache)
        .filter(DoclingCache.file_hash == package["file_hash"])
        .first()
    )
    package_path = str(directory / PACKAGE_FILENAME)
    if cache is None:
        cache = DoclingCache(
            paper_id=paper.id,
            file_hash=package["file_hash"],
            cache_dir=str(directory),
            docling_version=package.get("docling_version") or "imported",
        )
        db.add(cache)
    cache.markdown_path = str(directory / package["markdown_path"]) \
        if package.get("markdown_path") else None
    cache.page_count = package.get("page_count", 0)
    cache.table_count = len(package.get("tables") or [])
    cache.figure_count = len(package.get("figures") or [])
    cache.silver_package_path = package_path
    db.flush()


def register(db: Session, project_id: int, directory: Path) -> str:
    """Register one extracted directory. Returns "registered" or "updated"."""
    package, stamped = read_package(directory)
    if stamped:
        _stamp(directory, package)
    paper, created = _paper_for(db, project_id, package, directory)
    _cache_for(db, paper, package, directory)
    return "registered" if created else "updated"


def import_root(db: Session, project_id: int, root: Path,
                limit: int | None = None) -> ImportResult:
    """Register every package under `root`. Never raises on one bad paper.

    A corpus of a hundred directories will contain a truncated one, and failing the whole
    import for it would mean the other ninety-nine wait on a fix. The failure is collected
    with its reason and the run continues -- which is the same discipline the ingestion job
    applies to a paper whose model call fails.
    """
    result = ImportResult()
    directories = discover(root)
    if limit is not None:
        directories = directories[:limit]

    for directory in directories:
        try:
            outcome = register(db, project_id, directory)
            getattr(result, outcome).append(directory.name)
        except Exception as exc:
            logger.warning("%s: not a readable package (%s)", directory.name, exc)
            result.failed.append({"paper": directory.name, "reason": str(exc)[:300]})

    logger.info("Imported %d package(s) from %s: %d new, %d updated, %d failed",
                len(directories), root, len(result.registered), len(result.updated),
                len(result.failed))
    return result
