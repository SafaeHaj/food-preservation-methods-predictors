"""Write provenance anchors linking extracted values back to the PDF.

Evidence capture existed only on the `food_extraction` path, which also re-ran Docling from
scratch. The workspace path -- the one the UI actually drives -- produced no provenance at
all, so extracted numbers had nothing tying them to a page and a bounding box.

This builds the sink `science_writer` accepts, sourcing bounding boxes from the already-stored
`ExtractionAsset` rows instead of a fresh parse. Same provenance, no second Docling run.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from shared.config import get_common_settings
from shared.db.models import Evidence, ExtractionAsset

from app.services.evidence_capture import save_evidence_crop

logger = logging.getLogger(__name__)
_common = get_common_settings()


def _evidence_dir(paper_id: int) -> Path:
    directory = _common.storage_root / "evidence" / str(paper_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def build_reference_index(assets: list[ExtractionAsset]) -> dict[str, dict]:
    """{docling_item_ref: {bbox, page_number, is_chart}} from stored assets."""
    index: dict[str, dict] = {}
    for asset in assets:
        if not asset.docling_item_ref:
            continue
        bbox = None
        if asset.bbox_json:
            try:
                bbox = json.loads(asset.bbox_json)
            except json.JSONDecodeError:
                bbox = None
        index[asset.docling_item_ref] = {
            "bbox": bbox,
            "page_number": asset.page_number,
            "page_image_path": asset.page_image_path,
            "is_chart": asset.classification == "chart",
        }
    return index


def make_sink(
    db: Session, paper_id: int, pdf_path: str, reference_index: dict[str, dict]
):
    """Return an `EvidenceSink` that persists anchors and renders crops.

    Failures are logged and swallowed: provenance is an enrichment, and losing a crop must
    not fail an extraction that otherwise produced good data.
    """

    def sink(
        entity_type: str, entity_key: dict, field_name: Optional[str], evidence: dict
    ) -> None:
        try:
            item_ref = evidence.get("docling_item_ref")
            known = reference_index.get(item_ref, {}) if item_ref else {}
            bbox = known.get("bbox") or evidence.get("bounding_box") or {}
            page_number = evidence.get("page_number") or known.get("page_number")

            record = Evidence(
                paper_id=paper_id,
                entity_type=entity_type,
                entity_key=json.dumps(entity_key),
                field_name=field_name,
                page_number=page_number,
                source_type=evidence.get("source_type", "text"),
                source_label=evidence.get("source_label"),
                exact_text=evidence.get("exact_text"),
                bbox_x1=bbox.get("x1"),
                bbox_y1=bbox.get("y1"),
                bbox_x2=bbox.get("x2"),
                bbox_y2=bbox.get("y2"),
                confidence=evidence.get("confidence"),
                figure_series=evidence.get("figure_series"),
                x_axis_value=evidence.get("x_axis_value"),
                y_axis_value=evidence.get("y_axis_value"),
                value_is_approximate=bool(evidence.get("value_is_approximate", False)),
                docling_item_ref=item_ref,
                # Chart-derived values are estimates read off a plot; the flag travels with
                # the value so downstream modelling can weight it accordingly.
                is_chart_derived=bool(
                    evidence.get("source_type") == "chart_csv"
                    or evidence.get("value_is_approximate", False)
                    or known.get("is_chart", False)
                ),
            )
            db.add(record)
            db.flush()

            if page_number and bbox.get("x1") is not None:
                directory = _evidence_dir(paper_id)
                image_path = directory / f"ev_{record.id}.png"
                thumbnail_path = directory / f"thumb_{record.id}.png"
                if save_evidence_crop(pdf_path, page_number, bbox, image_path, thumbnail_path):
                    record.evidence_image_path = str(image_path)
                    record.evidence_thumbnail_path = str(thumbnail_path)
        except Exception:
            logger.warning(
                "Could not record %s evidence for paper %s", entity_type, paper_id, exc_info=True
            )

    return sink
