"""Assemble LLM evidence packages from stored assets.

Runs against `ExtractionAsset` / `AssetContextLink` rows rather than re-parsing the PDF, so
the LLM step is independent of Docling: a user can curate the asset selection in the
workspace and send it without paying for a second parse.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from shared.db.models import ExtractionAsset

from app.services.asset_selection import TEXT_LINK_TYPES
from app.services.evidence_package import EvidenceItem, EvidencePackage

logger = logging.getLogger(__name__)

#: Rough characters-per-token for budgeting. Deliberately conservative: overshooting the
#: model's context window fails the whole package, undershooting only costs a second call.
CHARS_PER_TOKEN = 4

#: Per-source content caps. Tables earn the largest budget (dense, structured, the highest
#: yield per token); chart CSVs are smaller and estimated; free text is the least reliable.
MAX_TABLE_CHARS = 4000
MAX_CHART_CSV_CHARS = 2000
MAX_PARAGRAPH_CHARS = 1500

#: Per-item overhead for the reference and framing the prompt adds around each item.
ITEM_OVERHEAD_CHARS = 100


def _read_csv(path: str | None, limit: int) -> str | None:
    if not path:
        return None
    file_path = Path(path)
    if not file_path.exists():
        return None
    try:
        content = file_path.read_text(encoding="utf-8")[:limit]
    except (OSError, UnicodeDecodeError):
        logger.warning("Could not read evidence CSV %s", path, exc_info=True)
        return None
    return content if content.strip() else None


def _bbox(asset: ExtractionAsset) -> dict | None:
    if not asset.bbox_json:
        return None
    try:
        return json.loads(asset.bbox_json)
    except json.JSONDecodeError:
        return None


def _items_for(asset: ExtractionAsset) -> list[EvidenceItem]:
    """Every evidence item one asset contributes: its data, then its context text."""
    items: list[EvidenceItem] = []
    reference = asset.docling_item_ref or f"asset_{asset.id}"
    page = asset.page_number or 0

    if asset.asset_type == "native_table":
        content = _read_csv(asset.csv_path, MAX_TABLE_CHARS)
        if content:
            items.append(
                EvidenceItem(
                    item_ref=reference,
                    page_number=page,
                    source_type="table",
                    source_label=asset.caption or f"Table (page {page})",
                    caption=asset.caption,
                    content=content,
                    bbox=_bbox(asset),
                    is_approximate=False,
                )
            )
    elif asset.asset_type == "figure":
        content = _read_csv(asset.csv_path, MAX_CHART_CSV_CHARS)
        if content:
            items.append(
                EvidenceItem(
                    item_ref=reference,
                    page_number=page,
                    source_type="chart_csv",
                    source_label=asset.caption or f"Figure (page {page})",
                    caption=asset.caption,
                    content=content,
                    bbox=_bbox(asset),
                    # Values read off a plot are estimates; the flag propagates all the way
                    # to Observation.value_origin so modelling can weight them accordingly.
                    is_approximate=True,
                )
            )

    for link in sorted(asset.context_links, key=lambda item: -(item.score or 0)):
        if link.link_type not in TEXT_LINK_TYPES:
            continue
        items.append(
            EvidenceItem(
                item_ref=link.item_ref or reference,
                page_number=link.page_number or page,
                source_type="text",
                source_label=asset.section_name or link.link_type,
                caption=None,
                content=link.text[:MAX_PARAGRAPH_CHARS],
                bbox=None,
                is_approximate=False,
            )
        )

    return items


def build_packages(
    assets: Iterable[ExtractionAsset], max_tokens_per_package: int = 3000
) -> tuple[list[EvidencePackage], set[str]]:
    """Group asset evidence into token-budgeted packages.

    Returns the packages and the set of docling item refs they cover, which the LLM prompt
    uses to constrain citations to references that actually exist.
    """
    max_chars = max_tokens_per_package * CHARS_PER_TOKEN
    items: list[EvidenceItem] = []
    known_refs: set[str] = set()

    for asset in assets:
        if asset.docling_item_ref:
            known_refs.add(asset.docling_item_ref)
        items.extend(_items_for(asset))

    if not items:
        return [], known_refs

    packages: list[EvidencePackage] = []
    current: list[EvidenceItem] = []
    current_chars = 0

    def flush() -> None:
        if current:
            packages.append(
                EvidencePackage(
                    index=len(packages) + 1,
                    items=list(current),
                    token_estimate=current_chars // CHARS_PER_TOKEN,
                )
            )

    for item in items:
        item_chars = len(item.content) + len(item.item_ref) + ITEM_OVERHEAD_CHARS
        if current and current_chars + item_chars > max_chars:
            flush()
            current, current_chars = [], 0
        current.append(item)
        current_chars += item_chars

    flush()
    return packages, known_refs
