"""
evidence_package.py — Build compact, LLM-ready evidence packages from Docling artefacts.

Instead of sending the full paper Markdown to the LLM, this module assembles
small "evidence packages" containing only:
  • Relevant text paragraphs (keyword-filtered, heading-aware)
  • ALL native tables (CSV content, already structured)
  • VALIDATED chart CSVs (labelled as approximate)
  • Captions and nearby headings for context
  • Docling item references for every included item

Each package is sized to fit comfortably within the LLM token budget
(default ≤ 3 000 tokens ≈ 12 000 chars).

The LLM is told to cite a docling_item_ref from the provided list for every
extracted value.  The evidence package builder records all valid refs so the
caller can validate LLM citations after extraction.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.services.docling_extractor import DoclingResult, DoclingText, DoclingTable, DoclingFigure
from app.services.chart_converter import ChartResult

logger = logging.getLogger(__name__)

# ─── Relevance filter ─────────────────────────────────────────────────────────

# Text paragraphs are included only if they contain at least one of these keywords
# (case-insensitive substring match).  Tables and valid chart CSVs are always included.
_RELEVANCE_KW = frozenset({
    # Time / storage
    "day", " d0", " d1", " d2", " d3", " d4", " d5", " d6", " d7",
    "d8", " d9", "d10", "d12", "d14", "d16", "d21",
    "storage", "shelf", "shelf-life", "shelf life",
    # Microbiology
    "cfu", "log cfu", "tvc", "total viable", "aerobic",
    "yeast", "mold", "mould", "coliform", "salmonella", "listeria",
    "staphylococcus", "lactic acid bacteria",
    # Chemistry / quality
    "ph", "tbars", "tvb-n", "tvb", "aw", "water activity",
    "oxidation", "peroxide", "acid value", "moisture",
    "colour", "color", "texture", "firmness", "hardness",
    # Treatments / ingredients
    "treatment", "control", "coating", "dip", "spray", "marination",
    "chitosan", "nisin", "thymol", "rosemary", "oregano", "thyme",
    "essential oil", "bacteriocin", "antimicrobial", "antioxidant",
    "concentration", "%, g/l, mg/kg, mg/g, mg/ml, au/ml",
    "preservation", "packaging", "vacuum", "modified atmosphere",
    # Meat types
    "beef", "chicken", "pork", "lamb", "turkey", "fish", "salmon",
    "fillet", "breast", "loin", "minced", "ground", "sausage",
    # Cheese / dairy
    "cheese", "milk", "whey", "casein", "ripening", "coagulation",
    # Statistical
    "p<", "p <", "p=", "significant", "mean", "std", "sd",
})

_HEADING_RELEVANCE_KW = frozenset({
    "material", "method", "result", "experiment", "treatment",
    "antimicrobial", "preservation", "quality", "measurement",
    "microbial", "chemical", "physical", "sensory", "storage",
})

MAX_TOKENS_PER_PACKAGE = 3_000   # ≈ 12 000 chars
_CHARS_PER_TOKEN = 4


def _is_relevant_text(txt: DoclingText) -> bool:
    """True if this text paragraph is likely to contain experiment data."""
    combined = (txt.text + " " + (txt.heading_context or "")).lower()
    return any(kw in combined for kw in _RELEVANCE_KW)


def _is_relevant_heading(heading: Optional[str]) -> bool:
    if not heading:
        return True  # include text with no heading context
    return any(kw in heading.lower() for kw in _HEADING_RELEVANCE_KW)


# ─── Evidence item ─────────────────────────────────────────────────────────────

@dataclass
class EvidenceItem:
    item_ref: str
    page_number: int
    source_type: str          # 'text' | 'table' | 'chart_csv'
    source_label: Optional[str]
    caption: Optional[str]
    content: str              # text paragraph / CSV string
    bbox: Optional[dict]
    is_approximate: bool = False   # True for chart-derived values


# ─── Evidence package ──────────────────────────────────────────────────────────

@dataclass
class EvidencePackage:
    index: int                              # 1-based package number
    items: list = field(default_factory=list)   # List[EvidenceItem]
    token_estimate: int = 0

    def render(self) -> str:
        """Render as a formatted string for the LLM user message."""
        parts = [f"=== EVIDENCE PACKAGE {self.index} ===\n"]
        for item in self.items:
            approx_note = "  [VALUES ARE APPROXIMATE — chart reading]" if item.is_approximate else ""
            header = (
                f"[{item.source_type.upper()}]"
                f" {item.source_label or ''}"
                f" (ref: {item.item_ref}, page: {item.page_number})"
                f"{approx_note}"
            )
            if item.caption:
                header += f"\nCaption: {item.caption}"
            parts.append(f"\n{header}\n{item.content}\n")
        return "\n".join(parts)


# ─── Builder ──────────────────────────────────────────────────────────────────

def build_packages(
    docling_result: DoclingResult,
    chart_results: list,
    max_tokens: int = MAX_TOKENS_PER_PACKAGE,
) -> list:
    """
    Build a list of EvidencePackage objects from Docling + Chart artefacts.

    Strategy:
      1. Always include all native tables (structured, high-confidence source).
      2. Include all validated chart CSVs (marked as approximate).
      3. Include text paragraphs that pass the relevance keyword filter.
      4. Split into packages so each fits within max_tokens.

    Returns list[EvidencePackage].  Empty list if no relevant evidence found.
    """
    max_chars = max_tokens * _CHARS_PER_TOKEN
    items: list = []

    # ── 1. Native tables ──────────────────────────────────────────────────────
    for tbl in docling_result.tables:
        if not tbl.csv_path or not Path(tbl.csv_path).exists():
            continue
        try:
            content = Path(tbl.csv_path).read_text(encoding="utf-8")
        except Exception:
            continue
        if not content.strip():
            continue
        items.append(EvidenceItem(
            item_ref=tbl.item_ref,
            page_number=tbl.page_number,
            source_type="table",
            source_label=tbl.caption or f"Table (page {tbl.page_number})",
            caption=tbl.caption,
            content=content[:4000],   # cap individual table at 4 000 chars
            bbox=tbl.bbox,
            is_approximate=False,
        ))

    # ── 2. Validated chart CSVs ───────────────────────────────────────────────
    chart_by_ref = {cr.item_ref: cr for cr in chart_results}
    for fig in docling_result.figures:
        cr = chart_by_ref.get(fig.item_ref)
        if not cr or cr.status != "valid" or not cr.csv_path:
            continue
        if not Path(cr.csv_path).exists():
            continue
        try:
            content = Path(cr.csv_path).read_text(encoding="utf-8")
        except Exception:
            continue
        if not content.strip():
            continue
        label = fig.caption or f"Figure {cr.figure_index} (page {fig.page_number})"
        items.append(EvidenceItem(
            item_ref=fig.item_ref,
            page_number=fig.page_number,
            source_type="chart_csv",
            source_label=label,
            caption=fig.caption,
            content=content[:2000],
            bbox=fig.bbox,
            is_approximate=True,
        ))

    # ── 3. Relevant text paragraphs ───────────────────────────────────────────
    for txt in docling_result.texts:
        if not _is_relevant_heading(txt.heading_context):
            continue
        if not _is_relevant_text(txt):
            continue
        items.append(EvidenceItem(
            item_ref=txt.item_ref,
            page_number=txt.page_number,
            source_type="text",
            source_label=txt.heading_context,
            caption=None,
            content=txt.text[:1500],
            bbox=txt.bbox,
            is_approximate=False,
        ))

    if not items:
        logger.info("Evidence package builder: no relevant items found.")
        return []

    # ── 4. Split into token-budget packages ───────────────────────────────────
    packages: list = []
    current_items: list = []
    current_chars = 0
    pkg_index = 1

    for item in items:
        item_chars = len(item.content) + len(item.item_ref) + 100  # 100 for header overhead
        if current_items and current_chars + item_chars > max_chars:
            packages.append(EvidencePackage(
                index=pkg_index,
                items=current_items,
                token_estimate=current_chars // _CHARS_PER_TOKEN,
            ))
            pkg_index += 1
            current_items = []
            current_chars = 0
        current_items.append(item)
        current_chars += item_chars

    if current_items:
        packages.append(EvidencePackage(
            index=pkg_index,
            items=current_items,
            token_estimate=current_chars // _CHARS_PER_TOKEN,
        ))

    logger.info(
        "Built %d evidence packages (%d items: %d tables, %d charts, %d text)",
        len(packages),
        len(items),
        sum(1 for i in items if i.source_type == "table"),
        sum(1 for i in items if i.source_type == "chart_csv"),
        sum(1 for i in items if i.source_type == "text"),
    )
    return packages
