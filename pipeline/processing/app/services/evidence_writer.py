"""Write provenance anchors linking extracted values back to the PDF.

This builds the sink `science_writer` accepts, sourcing bounding boxes from the
already-stored `ExtractionAsset` rows rather than re-parsing the document: an evidence span
names a `docling_item_ref`, and the asset written under that ref already knows its page and
its box.

The spans arriving here are validated `EvidenceSpan` records, so `method`, `source_type`
and `field_name` are guaranteed to satisfy the columns' CHECK constraints, and `confidence`
has been computed by `gold.evidence` rather than chosen by the model.

No image is rendered. A span carries the page, the box and the quote -- everything needed
to find and judge the claim -- and cropping it to a PNG needed a second PDF library and ran
eagerly inside the write transaction for thousands of spans nobody opened. The row is the
provenance; the picture was decoration.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from shared.db.models import Evidence, ExtractionAsset

logger = logging.getLogger(__name__)


def build_reference_index(db: Session, paper_id: int) -> dict[str, dict]:
    """{docling_item_ref: {bbox, page_number, is_chart}} from the paper's stored assets.

    A span cites a `docling_item_ref`; the asset extraction wrote under that ref already
    knows which page it was on and where. Reading it back is how a span gets coordinates
    without processing ever touching the PDF.
    """
    assets = (
        db.query(ExtractionAsset)
        .filter(ExtractionAsset.paper_id == paper_id,
                ExtractionAsset.docling_item_ref.isnot(None))
        .all()
    )
    index: dict[str, dict] = {}
    for asset in assets:
        bbox = None
        if asset.bbox_json:
            try:
                bbox = json.loads(asset.bbox_json)
            except json.JSONDecodeError:
                bbox = None
        index[asset.docling_item_ref] = {
            "bbox": bbox,
            "page_number": asset.page_number,
            "is_chart": asset.classification == "chart",
        }
    return index


def make_sink(db: Session, paper_id: int, reference_index: dict[str, dict]):
    """Return an `EvidenceSink` that persists anchors.

    It takes an `EvidenceSpan`, already validated: `method`, `source_type` and `field_name`
    are guaranteed to be values the columns accept, and `confidence` has been computed by
    the scorer rather than chosen by the model.

    Failures are logged and swallowed: provenance is an enrichment, and losing one anchor
    must not fail an extraction that otherwise produced good data.
    """

    def sink(
        entity_type: str, entity_key: dict, field_name: Optional[str], span
    ) -> None:
        try:
            item_ref = span.docling_item_ref
            known = reference_index.get(item_ref, {}) if item_ref else {}
            bbox = known.get("bbox") or {}
            page_number = span.page_number or known.get("page_number")

            record = Evidence(
                paper_id=paper_id,
                entity_type=entity_type,
                entity_key=json.dumps(entity_key),
                field_name=field_name or span.field_name,
                page_number=page_number,
                source_type=span.source_type,
                source_label=span.source_label,
                exact_text=span.exact_text,
                method=span.method,
                rationale=span.rationale,
                bbox_x1=bbox.get("x1"),
                bbox_y1=bbox.get("y1"),
                bbox_x2=bbox.get("x2"),
                bbox_y2=bbox.get("y2"),
                confidence=span.confidence,
                value_is_approximate=span.value_is_approximate,
                docling_item_ref=item_ref,
                # Chart-derived values are estimates read off a plot; the flag travels with
                # the value so downstream modelling can weight it accordingly.
                is_chart_derived=bool(
                    span.source_type == "figure"
                    or span.value_is_approximate
                    or known.get("is_chart", False)
                ),
            )
            db.add(record)
            db.flush()
        except Exception:
            logger.warning(
                "Could not record %s evidence for paper %s", entity_type, paper_id, exc_info=True
            )

    return sink
