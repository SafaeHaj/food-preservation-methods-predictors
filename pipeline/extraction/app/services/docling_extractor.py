"""
docling_extractor.py — Docling-based PDF extraction service.

For each PDF extracts:
  • Structured text paragraphs with page provenance
  • Native tables exported as CSV files
  • Figure images saved as PNG files
  • Per-item metadata: page_number, bounding_box (fractional 0-1), docling self_ref, caption

Results are cached on disk by file SHA-256 hash + DOCLING_CACHE_VERSION so each PDF
is processed only once.  The DB table DoclingCache records the cache location.

Raises ImportError when docling is not installed.
Raises RuntimeError on extraction failure.
API credentials never leave the server.
"""
import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from shared.config import get_extraction_settings

_settings = get_extraction_settings()

logger = logging.getLogger(__name__)

# Sections whose content we skip (conclusions add noise, refs are not experiments)
_SKIP_HEADINGS = frozenset({
    "conclusion", "conclusions", "references", "bibliography",
    "acknowledgement", "acknowledgements", "funding", "conflict",
    "appendix", "supplementary",
})


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class DoclingText:
    item_ref: str
    page_number: int
    text: str
    heading_context: Optional[str] = None
    bbox: Optional[dict] = None          # {x1, y1, x2, y2} fractional


@dataclass
class DoclingTable:
    item_ref: str
    page_number: int
    caption: Optional[str] = None
    csv_path: str = ""
    bbox: Optional[dict] = None


@dataclass
class DoclingFigure:
    item_ref: str
    page_number: int
    caption: Optional[str] = None
    image_path: str = ""
    bbox: Optional[dict] = None


@dataclass
class DoclingResult:
    file_hash: str
    cache_dir: str
    markdown_path: str
    texts: list = field(default_factory=list)     # List[DoclingText]
    tables: list = field(default_factory=list)    # List[DoclingTable]
    figures: list = field(default_factory=list)   # List[DoclingFigure]
    page_count: int = 0

    @property
    def known_item_refs(self) -> set:
        """All valid docling_item_ref values — used to validate LLM citations."""
        refs = set()
        for item in self.texts:
            refs.add(item.item_ref)
        for item in self.tables:
            refs.add(item.item_ref)
        for item in self.figures:
            refs.add(item.item_ref)
        return refs


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _file_hash(pdf_path: str) -> str:
    sha = hashlib.sha256()
    with open(pdf_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _bbox_fractional(prov_list, page_width: float, page_height: float) -> Optional[dict]:
    """Convert Docling provenance bbox to fractional {x1, y1, x2, y2}."""
    if not prov_list:
        return None
    try:
        bbox = prov_list[0].bbox
        # Docling BoundingBox: l/t/r/b in PDF points (top-left origin)
        # Handle both attribute styles gracefully.
        l = getattr(bbox, "l", None) if getattr(bbox, "l", None) is not None else getattr(bbox, "x1", 0)
        t = getattr(bbox, "t", None) if getattr(bbox, "t", None) is not None else getattr(bbox, "y1", 0)
        r = getattr(bbox, "r", None) if getattr(bbox, "r", None) is not None else getattr(bbox, "x2", page_width)
        b = getattr(bbox, "b", None) if getattr(bbox, "b", None) is not None else getattr(bbox, "y2", page_height)
        if page_width > 0 and page_height > 0:
            return {
                "x1": max(0.0, min(1.0, float(l) / page_width)),
                "y1": max(0.0, min(1.0, float(t) / page_height)),
                "x2": max(0.0, min(1.0, float(r) / page_width)),
                "y2": max(0.0, min(1.0, float(b) / page_height)),
            }
    except Exception:
        pass
    return None


def _page_size(doc, page_no: int) -> tuple:
    """Return (width, height) in PDF points for page_no (1-indexed). Falls back to Letter."""
    try:
        page = doc.pages[page_no]
        return float(page.size.width), float(page.size.height)
    except Exception:
        pass
    try:
        for pno, page in doc.pages.items():
            if pno == page_no:
                return float(page.size.width), float(page.size.height)
    except Exception:
        pass
    return 612.0, 792.0


def _caption_text(element, doc) -> Optional[str]:
    """Extract caption from a PictureItem or TableItem."""
    parts = []
    try:
        for cap in getattr(element, "captions", []):
            # Try different Docling versions
            text = (
                getattr(cap, "text", None)
                or getattr(cap, "ref_text", None)
            )
            if text is None:
                try:
                    resolved = cap.resolve(doc)
                    text = getattr(resolved, "text", None)
                except Exception:
                    pass
            if text:
                parts.append(text)
    except Exception:
        pass
    return " ".join(parts).strip() or None


# ─── Cache helpers ─────────────────────────────────────────────────────────────

def _write_cache(cache_dir: Path, result: DoclingResult) -> None:
    meta = {
        "docling_version": _settings.DOCLING_CACHE_VERSION,
        "file_hash": result.file_hash,
        "page_count": result.page_count,
        "table_count": len(result.tables),
        "figure_count": len(result.figures),
        "tables": [
            {
                "item_ref": t.item_ref,
                "page_number": t.page_number,
                "caption": t.caption,
                "csv_path": t.csv_path,
                "bbox": t.bbox,
            }
            for t in result.tables
        ],
        "figures": [
            {
                "item_ref": f.item_ref,
                "page_number": f.page_number,
                "caption": f.caption,
                "image_path": f.image_path,
                "bbox": f.bbox,
            }
            for f in result.figures
        ],
        "texts": [
            {
                "item_ref": t.item_ref,
                "page_number": t.page_number,
                "text": t.text,
                "heading_context": t.heading_context,
                "bbox": t.bbox,
            }
            for t in result.texts
        ],
    }
    (cache_dir / "cache_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _load_cache(file_hash: str, cache_dir: Path) -> Optional[DoclingResult]:
    meta_path = cache_dir / "cache_meta.json"
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("docling_version") != _settings.DOCLING_CACHE_VERSION:
            return None
        return DoclingResult(
            file_hash=file_hash,
            cache_dir=str(cache_dir),
            markdown_path=str(cache_dir / "content.md"),
            texts=[DoclingText(**t) for t in meta.get("texts", [])],
            tables=[DoclingTable(**t) for t in meta.get("tables", [])],
            figures=[DoclingFigure(**f) for f in meta.get("figures", [])],
            page_count=meta.get("page_count", 0),
        )
    except Exception as exc:
        logger.warning("Docling cache corrupt for %s: %s", file_hash, exc)
        return None


# ─── Main entry point ─────────────────────────────────────────────────────────

def extract_pdf(pdf_path: str) -> DoclingResult:
    """
    Extract PDF using Docling.  Results are cached on disk by SHA-256 hash.

    Returns a DoclingResult containing all texts, tables, and figures
    with per-item provenance.

    Raises ImportError if docling is not installed.
    Raises RuntimeError on extraction failure.
    """
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling_core.types.doc import PictureItem, TableItem
    except ImportError as exc:
        raise ImportError(
            "docling is not installed. Run: pip install 'docling>=2.14.0,<3.0'"
        ) from exc

    file_hash = _file_hash(pdf_path)
    base_dir = _settings.docling_cache_path
    cache_dir = base_dir / file_hash
    cache_dir.mkdir(parents=True, exist_ok=True)

    # ── Cache hit ─────────────────────────────────────────────────────────────
    cached = _load_cache(file_hash, cache_dir)
    if cached is not None:
        logger.info("Docling cache hit: %s", pdf_path)
        return cached

    # ── Fresh extraction ──────────────────────────────────────────────────────
    logger.info("Running Docling on %s …", pdf_path)

    pipeline_options = PdfPipelineOptions()
    pipeline_options.images_scale = 2.0
    pipeline_options.generate_page_images = False
    pipeline_options.generate_picture_images = True

    # GPU acceleration when available
    try:
        from docling.datamodel.pipeline_options import AcceleratorOptions, AcceleratorDevice
        import torch
        device = AcceleratorDevice.CUDA if torch.cuda.is_available() else AcceleratorDevice.CPU
        pipeline_options.accelerator_options = AcceleratorOptions(
            device=device, num_threads=4
        )
    except (ImportError, AttributeError):
        pass  # CPU default is fine

    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )
    try:
        conv_result = converter.convert(pdf_path)
    except Exception as exc:
        raise RuntimeError(f"Docling conversion failed for {pdf_path}: {exc}") from exc

    doc = conv_result.document

    # ── Mark skip zone (Conclusions / References and everything after) ────────
    skip_ids: set = set()
    skipping = False
    for item, _level in doc.iterate_items():
        raw_text = getattr(item, "text", "") or ""
        label = str(getattr(item, "label", "") or "").lower()
        if "heading" in label or "section_header" in label:
            if raw_text.lower().strip() in _SKIP_HEADINGS:
                skipping = True
        if skipping:
            skip_ids.add(id(item))

    # ── Iterate and collect ───────────────────────────────────────────────────
    texts: list = []
    tables: list = []
    figures: list = []
    pic_count = 0
    tbl_count = 0
    current_heading: Optional[str] = None

    for element, _level in doc.iterate_items():
        if id(element) in skip_ids:
            continue

        item_ref: str = getattr(element, "self_ref", None) or f"#/unknown/{id(element)}"
        prov = getattr(element, "prov", None) or []
        page_no: int = int(prov[0].page_no) if prov else 1
        w, h = _page_size(doc, page_no)
        bbox = _bbox_fractional(prov, w, h)
        label = str(getattr(element, "label", "") or "").lower()

        # Track current heading for text context
        if "heading" in label or "section_header" in label:
            current_heading = getattr(element, "text", "") or None

        if isinstance(element, TableItem):
            tbl_count += 1
            try:
                df = element.export_to_dataframe(doc)
            except TypeError:
                df = element.export_to_dataframe()
            csv_path = cache_dir / f"table_{tbl_count}.csv"
            df.to_csv(str(csv_path), index=False)
            tables.append(DoclingTable(
                item_ref=item_ref,
                page_number=page_no,
                caption=_caption_text(element, doc),
                csv_path=str(csv_path),
                bbox=bbox,
            ))

        elif isinstance(element, PictureItem):
            pic_count += 1
            img_path = cache_dir / f"image_{pic_count}.png"
            saved = False
            try:
                img = element.get_image(doc)
                if img:
                    img.save(str(img_path))
                    saved = True
            except Exception as exc:
                logger.warning("Figure %d save failed: %s", pic_count, exc)
            figures.append(DoclingFigure(
                item_ref=item_ref,
                page_number=page_no,
                caption=_caption_text(element, doc),
                image_path=str(img_path) if saved else "",
                bbox=bbox,
            ))

        else:
            raw_text = getattr(element, "text", "") or ""
            if raw_text.strip():
                texts.append(DoclingText(
                    item_ref=item_ref,
                    page_number=page_no,
                    text=raw_text,
                    heading_context=current_heading,
                    bbox=bbox,
                ))

    # ── Save Markdown ─────────────────────────────────────────────────────────
    md_path = cache_dir / "content.md"
    md_path.write_text(doc.export_to_markdown(), encoding="utf-8")

    page_count = len(doc.pages) if hasattr(doc, "pages") else 0
    result = DoclingResult(
        file_hash=file_hash,
        cache_dir=str(cache_dir),
        markdown_path=str(md_path),
        texts=texts,
        tables=tables,
        figures=figures,
        page_count=page_count,
    )

    _write_cache(cache_dir, result)
    logger.info(
        "Docling: %d texts, %d tables, %d figures from %s",
        len(texts), len(tables), len(figures), pdf_path,
    )
    return result
