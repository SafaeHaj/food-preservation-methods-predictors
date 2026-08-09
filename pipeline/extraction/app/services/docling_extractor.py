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
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from shared.config import get_extraction_settings

_settings = get_extraction_settings()

logger = logging.getLogger(__name__)

#: Threads Docling's own layout/table-structure inference may use. A plain env var, not a
#: Settings field: this only matters for the CPU batch runner, which sizes it to
#: cores-per-worker so N concurrent worker processes don't each claim every core (the
#: default of 4 is the historical, GPU-era value and stays put for the container).
_DOCLING_NUM_THREADS = int(os.environ.get("EXTRACTION_DOCLING_NUM_THREADS", "4"))

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
    #: Headings are kept as items rather than only as `heading_context` so Silver can
    #: segment the document into sections and find the methods without re-reading the
    #: markdown. A heading's own text is its section title.
    is_heading: bool = False
    #: Nesting depth, 1-based. Used to tell "2.1 Sample preparation" ending the methods
    #: from "3. Results" ending them.
    level: int = 1
    #: Position in reading order. `local_context` ranks by distance from an asset's own
    #: position, which is what makes context selection independent of any keyword list.
    order: int = 0


@dataclass
class DoclingTable:
    item_ref: str
    page_number: int
    caption: Optional[str] = None
    csv_path: str = ""
    bbox: Optional[dict] = None
    #: Position in reading order, shared with texts and figures, so Silver can find the
    #: prose nearest an asset without matching on words.
    order: int = 0


@dataclass
class DoclingFigure:
    item_ref: str
    page_number: int
    caption: Optional[str] = None
    image_path: str = ""
    bbox: Optional[dict] = None
    order: int = 0


@dataclass
class DoclingResult:
    file_hash: str
    cache_dir: str
    markdown_path: str
    texts: list = field(default_factory=list)     # List[DoclingText]
    tables: list = field(default_factory=list)    # List[DoclingTable]
    figures: list = field(default_factory=list)   # List[DoclingFigure]
    page_count: int = 0
    #: Whether the PDF carried its own text, and so whether OCR was run over it. Recorded
    #: because a paper that needed OCR costs several times one that did not, and because a
    #: batch that suddenly contains scans should be visible rather than just slow.
    #: `None` on a cache written before this was tracked.
    native_pdf: Optional[bool] = None
    ocr_enabled: Optional[bool] = None
    #: {page_number: PNG path}, rendered by Docling itself. The workspace previews used to
    #: come from a second PyMuPDF pass over the same PDF; Docling has already rasterised
    #: every page to find the figures, so asking it for them costs nothing extra.
    page_images: dict = field(default_factory=dict)

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


def pdf_looks_native(pdf_path: str) -> bool:
    """Does this PDF already carry its own text, or does it need to be read by OCR?

    Sampled rather than exhaustive: a paper's opening pages are the ones a scan would show
    as empty, and the whole corpus can be classified in seconds this way.

    `pypdfium2` rather than PyMuPDF because docling already installs it (docling-slim's
    `format-pdf` extra), so nothing new is pulled in for a three-second test. Any failure
    reads as "not native": an unreadable PDF should be given to OCR, not assumed clean.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:
        logger.warning("pypdfium2 is unavailable; running OCR on every paper")
        return False

    document = None
    try:
        document = pdfium.PdfDocument(pdf_path)
        characters = 0
        for index in range(min(_settings.NATIVE_TEXT_SAMPLE_PAGES, len(document))):
            page = document[index].get_textpage()
            characters += len((page.get_text_range() or "").strip())
            page.close()
        return characters >= _settings.NATIVE_TEXT_THRESHOLD
    except Exception as exc:
        logger.warning("Could not read text from %s (%s); assuming it needs OCR",
                       pdf_path, exc)
        return False
    finally:
        if document is not None:
            document.close()


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


def _heading_level(element, tree_level: int) -> int:
    """Nesting depth of a heading, 1-based.

    Docling reports it on the item where it knows it and only through the tree otherwise.
    Silver uses it to tell a methods subsection from the section that ends the methods, so
    a wrong-but-consistent depth is better than none.
    """
    for attribute in ("level", "heading_level"):
        value = getattr(element, attribute, None)
        if isinstance(value, int) and value > 0:
            return value
    return max(1, int(tree_level or 1))


def _save_page_images(doc, pages_dir: Path) -> dict:
    """Write Docling's own page rasters to disk. Returns {page_number: path}.

    Best-effort: a failure here costs the workspace preview thumbnails, not the extraction,
    so it is logged and the parse continues with whatever was written.
    """
    rendered: dict = {}
    try:
        pages_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.warning("Could not create %s; page previews will be unavailable", pages_dir)
        return rendered

    for page_number, page in (getattr(doc, "pages", None) or {}).items():
        image = getattr(getattr(page, "image", None), "pil_image", None)
        if image is None:
            continue
        path = pages_dir / f"page_{int(page_number):04d}.png"
        try:
            if not path.exists():
                image.save(str(path))
            rendered[int(page_number)] = str(path)
        except (OSError, ValueError) as exc:
            logger.warning("Could not save page %s: %s", page_number, exc)
    return rendered


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
        "native_pdf": result.native_pdf,
        "ocr_enabled": result.ocr_enabled,
        "table_count": len(result.tables),
        "figure_count": len(result.figures),
        "tables": [
            {
                "item_ref": t.item_ref,
                "page_number": t.page_number,
                "caption": t.caption,
                "csv_path": t.csv_path,
                "bbox": t.bbox,
                "order": t.order,
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
                "order": f.order,
            }
            for f in result.figures
        ],
        "page_images": {str(number): path for number, path in result.page_images.items()},
        "texts": [
            {
                "item_ref": t.item_ref,
                "page_number": t.page_number,
                "text": t.text,
                "heading_context": t.heading_context,
                "bbox": t.bbox,
                "is_heading": t.is_heading,
                "level": t.level,
                "order": t.order,
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
            page_images={int(number): path
                         for number, path in (meta.get("page_images") or {}).items()},
            # Absent on caches written before OCR became a per-paper decision. That is a
            # missing record, not a wrong one, so it stays None rather than guessing --
            # and it needs no DOCLING_CACHE_VERSION bump, because the parse itself is
            # unchanged for the born-digital papers such a cache holds.
            native_pdf=meta.get("native_pdf"),
            ocr_enabled=meta.get("ocr_enabled"),
        )
    except Exception as exc:
        logger.warning("Docling cache corrupt for %s: %s", file_hash, exc)
        return None


# ─── Converter singleton ──────────────────────────────────────────────────────

#: Lazy, process-wide, mirroring the chart model's own singleton in chart_converter.py.
#: A DocumentConverter is safe and intended to be reused across documents -- its pipeline
#: options are fixed by settings that don't change mid-process, and rebuilding it per call
#: means reloading the layout, table-structure and OCR models from scratch every time. That
#: cost is invisible when a process only ever handles one paper (today's per-paper Slurm
#: task); it is paid on every paper once a worker starts handling several in a row.
#:
#: Keyed on `do_ocr`, because that is the one option decided per paper rather than per
#: deployment. Keying it here rather than passing the flag into `convert()` is what makes
#: the saving real: a process that only ever sees born-digital papers never constructs an
#: OCR model at all.
_converters: dict = {}


def _get_converter(do_ocr: bool):
    if do_ocr in _converters:
        return _converters[do_ocr]

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pipeline_options = PdfPipelineOptions()
    pipeline_options.images_scale = _settings.IMAGES_SCALE
    pipeline_options.generate_page_images = True
    pipeline_options.generate_picture_images = True
    pipeline_options.do_table_structure = _settings.TABLE_STRUCTURE
    pipeline_options.do_ocr = do_ocr

    # `accurate` reads merged and multi-row headers better and costs several times as long
    # per page, which is why it is a setting rather than a decision made here.
    try:
        from docling.datamodel.pipeline_options import TableFormerMode
        pipeline_options.table_structure_options.mode = (
            TableFormerMode.ACCURATE
            if _settings.TABLE_STRUCTURE_MODE.lower() == "accurate"
            else TableFormerMode.FAST
        )
    except (ImportError, AttributeError):
        pass

    # GPU acceleration when available
    try:
        from docling.datamodel.pipeline_options import AcceleratorOptions, AcceleratorDevice
        import torch
        device = AcceleratorDevice.CUDA if torch.cuda.is_available() else AcceleratorDevice.CPU
        pipeline_options.accelerator_options = AcceleratorOptions(
            device=device, num_threads=_DOCLING_NUM_THREADS
        )
    except (ImportError, AttributeError):
        pass  # CPU default is fine

    _converters[do_ocr] = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )
    return _converters[do_ocr]


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
    native = pdf_looks_native(pdf_path)
    logger.info("Running Docling on %s (native text: %s, OCR: %s) …",
                pdf_path, native, "off" if native else "on")

    converter = _get_converter(do_ocr=not native)
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

    order = 0
    for element, tree_level in doc.iterate_items():
        if id(element) in skip_ids:
            continue

        item_ref: str = getattr(element, "self_ref", None) or f"#/unknown/{id(element)}"
        prov = getattr(element, "prov", None) or []
        page_no: int = int(prov[0].page_no) if prov else 1
        w, h = _page_size(doc, page_no)
        bbox = _bbox_fractional(prov, w, h)
        label = str(getattr(element, "label", "") or "").lower()
        order += 1

        # Track current heading for text context
        is_heading = "heading" in label or "section_header" in label
        if is_heading:
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
                order=order,
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
                order=order,
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
                    is_heading=is_heading,
                    level=_heading_level(element, tree_level),
                    order=order,
                ))

    page_images = _save_page_images(doc, cache_dir / "pages")

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
        page_images=page_images,
        native_pdf=native,
        ocr_enabled=not native,
    )

    _write_cache(cache_dir, result)
    logger.info(
        "Docling: %d texts, %d tables, %d figures from %s",
        len(texts), len(tables), len(figures), pdf_path,
    )
    return result
