"""The Docling workspace pipeline: PDF in, classified and scored assets out.

Extracted verbatim in behaviour from the 280-line function that lived inside the route
module, where it opened its own session, committed ten times, and reported progress by
mutating the same `Job` row it was holding a transaction on.

Structure now:
  * each stage is a function that does one thing;
  * progress is published by `JobProgressReporter` on its own session;
  * the asset writes are one transaction.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from shared.config import get_extraction_settings
from shared.db.models import ExtractionAsset, Paper
from shared.uow import JobProgressReporter

from app.repositories import asset_repo
from app.services.asset_classifier import classify_figure, score_relevance
from app.services.chart_converter import convert_charts
from app.services.context_linker import build_context_links
from app.services.docling_extractor import extract_pdf

logger = logging.getLogger(__name__)
_settings = get_extraction_settings()


@dataclass(frozen=True)
class Stage:
    """One pipeline stage: the progress it reports and the message it shows.

    Named stages replace the bare integers that were scattered through the old function and
    mirrored -- separately, and inconsistently -- by a hardcoded stage table in the frontend.
    """

    key: str
    progress: int
    label: str


STAGES = {
    stage.key: stage
    for stage in (
        Stage("parse", 5, "Parsing document structure with Docling"),
        Stage("pages", 25, "Rendering page images"),
        Stage("assets", 35, "Saving figures and tables to the workspace"),
        Stage("linking", 50, "Linking context to visual elements"),
        Stage("charts", 65, "Converting charts to data"),
        Stage("scoring", 85, "Classifying and scoring assets"),
        Stage("manifest", 95, "Writing the asset manifest"),
        Stage("done", 100, "Extraction complete"),
    )
}


@dataclass
class PipelineOutcome:
    page_count: int
    figures: int
    native_tables: int
    charts: int
    decorative_excluded: int
    chart_conversion_available: bool

    def as_dict(self) -> dict:
        return {
            "page_count": self.page_count,
            "figures": self.figures,
            "native_tables": self.native_tables,
            "charts": self.charts,
            "decorative_excluded": self.decorative_excluded,
            "chart_conversion_available": self.chart_conversion_available,
        }


def render_page_images(pdf_path: str, pages_dir: Path) -> dict[int, str]:
    """Render every page to PNG. Returns {page_number: path}.

    Best-effort: a failure here costs the preview thumbnails, not the extraction, so it is
    logged and the pipeline continues with an empty map.
    """
    pages_dir.mkdir(parents=True, exist_ok=True)
    rendered: dict[int, str] = {}
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF is not installed; page previews will be unavailable")
        return rendered

    try:
        document = fitz.open(pdf_path)
    except Exception:
        logger.warning("Could not open %s for page rendering", pdf_path, exc_info=True)
        return rendered

    try:
        matrix = fitz.Matrix(_settings.PAGE_RENDER_ZOOM, _settings.PAGE_RENDER_ZOOM)
        for index in range(len(document)):
            page_number = index + 1
            image_path = pages_dir / f"page_{page_number:04d}.png"
            if not image_path.exists():
                document.load_page(index).get_pixmap(matrix=matrix, alpha=False).save(str(image_path))
            rendered[page_number] = str(image_path)
    except Exception:
        logger.warning("Page rendering stopped early for %s", pdf_path, exc_info=True)
    finally:
        document.close()
    return rendered


def write_manifest(cache_dir: Path, assets: list[ExtractionAsset]) -> None:
    """Write `item_manifest.jsonl`, the on-disk index alongside the cached parse."""
    try:
        with (cache_dir / "item_manifest.jsonl").open("w", encoding="utf-8") as handle:
            for asset in assets:
                handle.write(
                    json.dumps(
                        {
                            "id": asset.id,
                            "item_ref": asset.docling_item_ref,
                            "type": asset.asset_type,
                            "page_number": asset.page_number,
                            "bbox": json.loads(asset.bbox_json) if asset.bbox_json else None,
                            "section": asset.section_name,
                            "caption": asset.caption,
                            "image_path": asset.image_path,
                            "csv_path": asset.csv_path,
                            "classification": asset.classification,
                            "relevance_score": asset.relevance_score,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    except OSError:
        logger.warning("Could not write the asset manifest in %s", cache_dir, exc_info=True)


def _persist_assets(
    db: Session, paper_id: int, project_id: int, job_id: int,
    docling_result, page_images: dict[int, str],
) -> dict[str, int]:
    """Replace the paper's assets with the fresh parse. Returns {item_ref: asset_id}."""
    asset_repo.delete_for_paper(db, paper_id)
    db.flush()

    by_reference: dict[str, int] = {}

    for figure in docling_result.figures:
        asset = ExtractionAsset(
            paper_id=paper_id,
            project_id=project_id,
            job_id=job_id,
            docling_item_ref=figure.item_ref,
            asset_type="figure",
            page_number=figure.page_number,
            bbox_json=json.dumps(figure.bbox) if figure.bbox else None,
            caption=figure.caption,
            image_path=figure.image_path or None,
            page_image_path=page_images.get(figure.page_number),
            classification="unknown",
            conversion_status="pending" if figure.image_path else "skipped",
            relevance_score=0.0,
            selected_for_llm=False,
        )
        db.add(asset)
        db.flush()
        by_reference[figure.item_ref] = asset.id

    for table in docling_result.tables:
        rows, columns = asset_repo.csv_dimensions(table.csv_path)
        asset = ExtractionAsset(
            paper_id=paper_id,
            project_id=project_id,
            job_id=job_id,
            docling_item_ref=table.item_ref,
            asset_type="native_table",
            page_number=table.page_number,
            bbox_json=json.dumps(table.bbox) if table.bbox else None,
            caption=table.caption,
            csv_path=table.csv_path,
            page_image_path=page_images.get(table.page_number),
            classification="native_table",
            conversion_status="not_applicable",
            csv_rows=rows,
            csv_cols=columns,
            relevance_score=0.0,
            selected_for_llm=False,
        )
        db.add(asset)
        db.flush()
        by_reference[table.item_ref] = asset.id

    return by_reference


def _link_context(db: Session, docling_result, by_reference: dict[str, int]) -> None:
    for kind, items in (("figure", docling_result.figures), ("native_table", docling_result.tables)):
        for index, item in enumerate(items):
            asset_id = by_reference.get(item.item_ref)
            if not asset_id:
                continue
            asset_repo.add_context_links(
                db,
                asset_id,
                build_context_links(
                    docling_result, item.item_ref, kind, item.page_number, item.caption, index
                ),
            )


def _apply_chart_conversions(db: Session, docling_result, by_reference: dict[str, int]) -> int:
    """Attach converted chart CSVs to their assets. Returns the number of charts found."""
    conversions = {result.item_ref: result for result in convert_charts(
        docling_result.figures, docling_result.cache_dir
    )}
    charts = 0

    for figure in docling_result.figures:
        asset_id = by_reference.get(figure.item_ref)
        if not asset_id:
            continue
        asset = db.query(ExtractionAsset).filter(ExtractionAsset.id == asset_id).first()
        if not asset:
            continue

        conversion = conversions.get(figure.item_ref)
        if not conversion:
            asset.conversion_status = "skipped"
            continue

        if conversion.status == "valid":
            asset.conversion_status = "complete"
            asset.csv_path = conversion.csv_path
            asset.csv_rows = conversion.row_count
            asset.csv_cols = conversion.col_count
            charts += 1
        elif conversion.status == "rejected":
            # "Rejected" means the converter looked and decided it was not a chart -- a
            # normal outcome for a photograph, not a failure worth surfacing as an error.
            asset.conversion_status = "not_a_chart"
            asset.conversion_error = conversion.reject_reason
        elif conversion.status == "error":
            asset.conversion_status = "failed"
            asset.conversion_error = conversion.reject_reason
        else:
            asset.conversion_status = "skipped"

    return charts


#: Context snippets fed to the relevance scorer per asset. More adds noise, not signal.
MAX_SCORING_CONTEXT_LINKS = 10


def _classify_and_score(db: Session, paper_id: int) -> tuple[int, list[ExtractionAsset]]:
    """Classify every figure and score every asset. Returns (decorative count, assets)."""
    assets = asset_repo.all_for_paper_with_links(db, paper_id)
    decorative = 0

    for asset in assets:
        if asset.asset_type == "figure":
            asset.classification = classify_figure(
                asset.image_path, asset.csv_path, asset.csv_rows, asset.csv_cols,
                asset.caption, asset.conversion_status,
                page_number=asset.page_number, item_ref=asset.docling_item_ref,
            )
            if asset.classification in _settings.NON_SCIENTIFIC_CLASSIFICATIONS:
                decorative += 1

        # Scoring runs after classification because it consumes the classification.
        asset.relevance_score = score_relevance(
            asset.caption,
            asset.section_name,
            [link.text for link in asset.context_links[:MAX_SCORING_CONTEXT_LINKS]],
            asset.asset_type,
            classification=asset.classification,
            page_number=asset.page_number,
            item_ref=asset.docling_item_ref,
        )

    return decorative, assets


def run(db: Session, paper: Paper, job_id: int, progress: JobProgressReporter) -> PipelineOutcome:
    """Run the full pipeline for one paper.

    Raises on failure; the calling task translates that into a failed `Job`. The pipeline
    itself no longer catches-and-marks, which is what previously turned a Docling import
    error and a corrupt PDF into indistinguishable outcomes.
    """
    progress.update(progress=STAGES["parse"].progress, step=STAGES["parse"].label)
    docling_result = extract_pdf(paper.file_path)

    progress.update(
        progress=STAGES["pages"].progress,
        step=f"Rendering {docling_result.page_count} page images",
    )
    cache_dir = Path(docling_result.cache_dir)
    page_images = render_page_images(paper.file_path, cache_dir / "pages")

    progress.update(
        progress=STAGES["assets"].progress,
        step=(
            f"Saving {len(docling_result.figures)} figures and "
            f"{len(docling_result.tables)} tables"
        ),
    )
    by_reference = _persist_assets(
        db, paper.id, paper.project_id, job_id, docling_result, page_images
    )

    progress.update(progress=STAGES["linking"].progress, step=STAGES["linking"].label)
    _link_context(db, docling_result, by_reference)

    progress.update(
        progress=STAGES["charts"].progress,
        step=f"Converting {len(docling_result.figures)} figures with PP-Chart2Table",
    )
    charts = _apply_chart_conversions(db, docling_result, by_reference)

    progress.update(progress=STAGES["scoring"].progress, step=STAGES["scoring"].label)
    decorative, assets = _classify_and_score(db, paper.id)

    progress.update(progress=STAGES["manifest"].progress, step=STAGES["manifest"].label)
    write_manifest(cache_dir, assets)

    paper.page_count = docling_result.page_count

    from app.services.chart_converter import _chart_model_error

    return PipelineOutcome(
        page_count=docling_result.page_count,
        figures=len(docling_result.figures),
        native_tables=len(docling_result.tables),
        charts=charts,
        decorative_excluded=decorative,
        chart_conversion_available=_chart_model_error is None,
    )
