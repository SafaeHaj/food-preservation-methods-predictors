"""Where extraction left a paper's gated package.

Keyed on the file hash, like the Docling cache row it sits beside, so the same PDF uploaded
into two projects finds the parse already done.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from shared.db.models import DoclingCache


def silver_package_path(db: Session, file_hash: str) -> Optional[str]:
    cache = db.query(DoclingCache).filter(DoclingCache.file_hash == file_hash).first()
    return cache.silver_package_path if cache else None
