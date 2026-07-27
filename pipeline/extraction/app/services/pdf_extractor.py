"""
Full PDF extraction service.

Removes the legacy 8000-char limit. Extracts:
  - Full text, page by page
  - Tables (using PyMuPDF find_tables)
  - Figure captions

Returns typed chunks ready for the AI extractor.
Backward-compatible: legacy callers using extract_text_pages / extract_full_text still work.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class PageChunk:
    chunk_type: str           # page | table | figure_caption
    page_number: int
    section_name: str
    text_content: str
    has_table: bool = False
    table_data: Optional[list[list[str]]] = None
    bbox: Optional[list[float]] = None
    table_number: Optional[int] = None
    token_estimate: int = 0


_SECTION_PREFIXES = [
    "abstract", "introduction", "material", "method", "result",
    "discussion", "conclusion", "supplementar", "appendix",
]


def _detect_section(text: str) -> str:
    first_line = text.strip().split("\n")[0].lower()
    for prefix in _SECTION_PREFIXES:
        if first_line.startswith(prefix):
            return first_line[:80]
    return ""


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def extract_file_hash(file_path: str) -> str:
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            sha.update(block)
    return sha.hexdigest()


def extract_chunks(file_path: str) -> tuple[int, list[PageChunk]]:
    """
    Extract all content from a PDF into typed chunks.
    Returns (page_count, chunks).
    No character limit — every page is processed.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("PyMuPDF (fitz) is required: pip install pymupdf")

    doc = fitz.open(file_path)
    page_count = len(doc)
    chunks: list[PageChunk] = []
    table_counter = 0
    current_section = "preamble"

    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")
        if not text.strip():
            continue

        detected = _detect_section(text)
        if detected:
            current_section = detected

        chunks.append(PageChunk(
            chunk_type="page",
            page_number=page_num,
            section_name=current_section,
            text_content=text,
            token_estimate=_estimate_tokens(text),
        ))

        # Tables
        try:
            for table in page.find_tables():
                table_counter += 1
                rows = table.extract()
                if not rows:
                    continue
                table_md = _table_to_markdown(rows)
                chunks.append(PageChunk(
                    chunk_type="table",
                    page_number=page_num,
                    section_name=current_section,
                    text_content=table_md,
                    has_table=True,
                    table_data=rows,
                    bbox=list(table.bbox) if hasattr(table, "bbox") else None,
                    table_number=table_counter,
                    token_estimate=_estimate_tokens(table_md),
                ))
        except Exception:
            pass

        # Figure captions (heuristic: lines starting with "Fig")
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.lower().startswith("fig") and len(stripped) > 10:
                chunks.append(PageChunk(
                    chunk_type="figure_caption",
                    page_number=page_num,
                    section_name=current_section,
                    text_content=stripped,
                    token_estimate=_estimate_tokens(stripped),
                ))
                break

    doc.close()
    return page_count, chunks


def _table_to_markdown(rows: list[list]) -> str:
    if not rows:
        return ""
    lines = []
    header = [str(c or "").strip() for c in rows[0]]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in rows[1:]:
        cells = [str(c or "").strip().replace("\n", " ") for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


# ── Backward-compatible legacy API ────────────────────────────────────────

def extract_text_pages(pdf_path: str) -> Tuple[List[str], int]:
    """Returns (pages_text_list, page_count). One string per page."""
    page_count, chunks = extract_chunks(pdf_path)
    page_texts: dict[int, str] = {}
    for c in chunks:
        if c.chunk_type == "page":
            page_texts[c.page_number] = c.text_content
    ordered = [page_texts[n] for n in sorted(page_texts)]
    return ordered, page_count


def extract_full_text(pdf_path: str) -> Tuple[str, int]:
    """Returns (full_text, page_count). No length limit."""
    pages, count = extract_text_pages(pdf_path)
    return "\n\n--- PAGE BREAK ---\n\n".join(pages), count
