"""
evidence_capture.py — PDF page rendering and bounding-box cropping.

Uses PyMuPDF (fitz) to:
  1. Render full PDF pages as PNG bytes / base64 (for sending to vision models).
  2. Crop a bounding-box region from a page and save as a PNG evidence image.
  3. Generate 200 px-wide thumbnails of those crops (requires Pillow).

Bounding boxes are always in fractional page coordinates:
    {"x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 1.0}
where (0,0) is the top-left corner and (1,1) is the bottom-right.
"""
import base64
import io
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

RENDER_DPI = 150           # DPI for full-page renders sent to the vision model
CROP_DPI   = 200           # DPI for evidence crops saved to disk
THUMB_WIDTH = 300          # px width for thumbnails


def _fitz():
    try:
        import fitz
        return fitz
    except ImportError:
        raise RuntimeError("pymupdf is not installed — run: pip install pymupdf")


def _pil():
    try:
        from PIL import Image
        return Image
    except ImportError:
        raise RuntimeError("Pillow is not installed — run: pip install Pillow")


# ─── Page image utilities ──────────────────────────────────────────────────────

def render_page_base64(pdf_path: str, page_number: int, dpi: int = RENDER_DPI) -> str:
    """Render a single PDF page (1-indexed) and return base64-encoded PNG."""
    fitz = _fitz()
    doc = fitz.open(pdf_path)
    try:
        page = doc.load_page(page_number - 1)
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return base64.b64encode(pix.tobytes("png")).decode()
    finally:
        doc.close()


def render_all_pages_base64(pdf_path: str, max_pages: int = 30) -> list[tuple[int, str]]:
    """Render all pages (up to max_pages) and return list of (page_num, base64)."""
    fitz = _fitz()
    doc = fitz.open(pdf_path)
    results = []
    try:
        n = min(len(doc), max_pages)
        zoom = RENDER_DPI / 72.0
        mat = fitz.Matrix(zoom, zoom)
        for i in range(n):
            page = doc.load_page(i)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            b64 = base64.b64encode(pix.tobytes("png")).decode()
            results.append((i + 1, b64))
    finally:
        doc.close()
    return results


def identify_data_pages(pdf_path: str) -> list[int]:
    """
    Return 1-indexed page numbers that are likely to contain tables, figures,
    or dense numerical data. Used to select which pages to send as images.
    """
    fitz = _fitz()
    doc = fitz.open(pdf_path)
    data_pages = []
    try:
        for i in range(len(doc)):
            page = doc.load_page(i)
            text = page.get_text("text").lower()
            # Has a table detected by PyMuPDF
            has_table = bool(page.find_tables().tables)
            # Text heuristics: mentions of figure, table, or many digits
            digit_density = sum(c.isdigit() for c in text) / max(len(text), 1)
            mentions_fig_or_table = any(
                kw in text for kw in ("figure", "fig.", "table", "tbars", "cfu", "log cfu")
            )
            if has_table or digit_density > 0.04 or mentions_fig_or_table:
                data_pages.append(i + 1)
    finally:
        doc.close()
    return data_pages


# ─── Evidence image crop ───────────────────────────────────────────────────────

def save_evidence_crop(
    pdf_path: str,
    page_number: int,
    bbox: dict,               # {"x1": 0-1, "y1": 0-1, "x2": 0-1, "y2": 0-1}
    output_path: Path,
    thumb_path: Optional[Path] = None,
) -> bool:
    """
    Crop the bounding-box region from the page and save as PNG.
    Optionally saves a THUMB_WIDTH-wide thumbnail to thumb_path.
    Returns True on success, False on any error.
    """
    fitz = _fitz()
    try:
        doc = fitz.open(pdf_path)
        page = doc.load_page(page_number - 1)
        rect = page.rect  # (0, 0, width_pt, height_pt)

        # Convert fractional bbox to point coordinates
        x1 = float(bbox.get("x1", 0)) * rect.width
        y1 = float(bbox.get("y1", 0)) * rect.height
        x2 = float(bbox.get("x2", 1)) * rect.width
        y2 = float(bbox.get("y2", 1)) * rect.height

        # Guard against inverted or zero-area boxes
        if x2 <= x1 or y2 <= y1:
            doc.close()
            return False

        clip = fitz.Rect(x1, y1, x2, y2)
        zoom = CROP_DPI / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        pix.save(str(output_path))
        doc.close()

        # Generate thumbnail if requested
        if thumb_path is not None:
            _save_thumbnail(output_path, thumb_path)

        return True

    except Exception as exc:
        logger.warning("evidence_capture: failed to crop page %d of %s: %s", page_number, pdf_path, exc)
        return False


def _save_thumbnail(source_path: Path, thumb_path: Path) -> None:
    """Resize the evidence image to THUMB_WIDTH px wide and save."""
    try:
        Image = _pil()
        with Image.open(source_path) as img:
            w, h = img.size
            ratio = THUMB_WIDTH / w
            new_h = int(h * ratio)
            thumb = img.resize((THUMB_WIDTH, new_h), Image.LANCZOS)
            thumb_path.parent.mkdir(parents=True, exist_ok=True)
            thumb.save(str(thumb_path), "PNG")
    except Exception as exc:
        logger.warning("evidence_capture: failed to generate thumbnail %s: %s", thumb_path, exc)
