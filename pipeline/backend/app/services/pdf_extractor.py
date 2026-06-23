"""Extract plain text from PDF files using PyMuPDF."""
from pathlib import Path
from typing import List, Tuple


def extract_text_pages(pdf_path: str) -> Tuple[List[str], int]:
    """
    Returns (pages_text_list, page_count).
    Each item in pages_text_list is the text of one page.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("PyMuPDF (fitz) is not installed. Run: pip install pymupdf")

    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return pages, len(pages)


def extract_full_text(pdf_path: str) -> Tuple[str, int]:
    """Returns (full_text, page_count)."""
    pages, count = extract_text_pages(pdf_path)
    return "\n\n--- PAGE BREAK ---\n\n".join(pages), count
