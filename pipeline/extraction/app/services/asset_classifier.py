"""
asset_classifier.py — Visual validation and scientific relevance scoring.

classify_figure():
  Returns one of: chart | native_table | photograph | diagram |
                  chemical_structure | multi_panel_figure |
                  publisher_logo | license_icon | decorative_asset | unknown

score_relevance():
  Returns 0.0–10.0 — higher = more likely to contain extractable quantitative data.
  publisher_logo / license_icon / decorative_asset always return 0.0.
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Non-scientific asset detection ───────────────────────────────────────────

# Caption/filename patterns that reliably indicate logos, icons, decorative items.
_LOGO_PATTERNS = re.compile(
    r'\b(logo|logotype|banner|journal\s+logo|publisher\s+logo|'
    r'mdpi|elsevier|springer|wiley|taylor|francis|hindawi|frontiers|'
    r'crossmark|crossref|open\s+access|creative\s+commons|cc\s+by|'
    r'copyright|©|orcid)\b',
    re.IGNORECASE,
)
_LICENSE_PATTERNS = re.compile(
    r'\b(cc[-\s]by|creative\s+commons|open\s+access|'
    r'license|licence|copyright\s+notice)\b',
    re.IGNORECASE,
)

# Very short captions (< 20 chars) on page 1 with no scientific keywords are
# treated as decorative unless they look like "Figure N" references.
_NON_SCIENTIFIC_CAPTIONS = re.compile(
    r'^(graphical\s+abstract|table\s+of\s+contents|toc|'
    r'for\s+table\s+of\s+contents|'
    r'supplementary|supporting\s+information\s+only)$',
    re.IGNORECASE,
)

# Known non-scientific item_ref patterns produced by Docling for cover images.
_COVER_PAGE_ITEM_REFS = re.compile(r'pictures/\d+$', re.IGNORECASE)

_NON_SCIENTIFIC_CLASSES = frozenset({
    "publisher_logo", "license_icon", "decorative_asset",
})


def _is_decorative(caption: Optional[str], page_number: Optional[int],
                   item_ref: Optional[str]) -> Optional[str]:
    """
    Return a non-scientific class if the asset is clearly not scientific data,
    or None if it could be scientific.
    """
    cap = (caption or "").strip().lower()

    if _LOGO_PATTERNS.search(cap):
        return "publisher_logo"

    if _LICENSE_PATTERNS.search(cap):
        return "license_icon"

    if cap and _NON_SCIENTIFIC_CAPTIONS.match(cap):
        return "decorative_asset"

    # Very short captions on early pages with no scientific keywords are suspicious.
    # Only flag if we have no positive signal at all.
    if cap and len(cap) < 25 and page_number and page_number <= 2:
        has_sci = any(kw in cap for kw in (
            "fig", "table", "count", "cfu", "log", "ph", "aw", "tvc",
            "treatment", "concentration", "effect", "change",
        ))
        if not has_sci:
            return "decorative_asset"

    return None


# ─── Relevance scoring weights ────────────────────────────────────────────────

_SCORE_MAP = {
    # Microbiology — high value
    "total viable count": 2, "tvc": 2, "cfu": 2, "log cfu": 2, "aerobic": 1,
    "yeast": 1, "mold": 1, "mould": 1, "coliform": 1, "salmonella": 1,
    "listeria": 1, "staphylococcus": 1, "lactic acid bacteria": 1,
    # Chemical quality — high value
    "ph": 2, "tbars": 2, "tvb-n": 2, "tvb": 1, "water activity": 2, "aw ": 1,
    "oxidation": 1, "peroxide": 1, "acid value": 1,
    # Physical quality
    "color": 1, "colour": 1, "texture": 1, "firmness": 1, "hardness": 1, "moisture": 1,
    # Time / storage
    "storage day": 2, "shelf life": 2, "shelf-life": 2,
    "day 0": 1, "day 3": 1, "day 7": 1, "day 14": 1,
    # Treatments / ingredients
    "chitosan": 1, "nisin": 1, "thymol": 1, "rosemary": 1, "oregano": 1,
    "essential oil": 1, "bacteriocin": 1, "antimicrobial": 1, "antioxidant": 1,
    "control": 1, "treatment": 1, "coating": 1, "concentration": 1,
    # Matrices
    "beef": 1, "chicken": 1, "pork": 1, "lamb": 1, "fish": 1, "salmon": 1,
    "sausage": 1, "minced": 1, "ground meat": 1,
    "cheese": 1, "milk": 1, "whey": 1, "casein": 1,
    # Statistical signals
    "significant": 0.5, "p<0.05": 1, "p < 0.05": 1, "mean ±": 0.5,
}

_HIGH_SECTIONS = frozenset({
    "results", "result", "results and discussion",
    "microbial quality", "physicochemical", "chemical quality",
    "oxidative stability", "sensory", "shelf life", "shelf-life evaluation",
})
_LOW_SECTIONS = frozenset({
    "introduction", "materials and methods", "materials", "methods",
    "statistical analysis", "statistics", "conclusion", "conclusions",
    "references", "bibliography", "acknowledgements", "funding",
})

# ─── Caption patterns for figure classification ───────────────────────────────

_CHART_CAPTIONS = re.compile(
    r'\b(count|cfu|log|ph|tbars|tvb|tvc|growth|color|colour|firmness|'
    r'texture|hardness|moisture|oxidation|aw|water activity|'
    r'change|effect|evolution|variation|trend)\b',
    re.IGNORECASE,
)
_DIAGRAM_CAPTIONS = re.compile(
    r'\b(schematic|diagram|flow|process|pathway|mechanism|model|map)\b',
    re.IGNORECASE,
)
_CHEMICAL_CAPTIONS = re.compile(
    r'\b(structure|compound|molecule|formula|chemical|polymer|monomer)\b',
    re.IGNORECASE,
)
_PANEL_CAPTIONS = re.compile(r'\bpanel\b|\([a-dA-D]\)', re.IGNORECASE)


# ─── Public API ───────────────────────────────────────────────────────────────

def score_relevance(
    caption: Optional[str],
    section_name: Optional[str],
    context_texts: list,
    asset_type: str = "figure",
    classification: Optional[str] = None,
    page_number: Optional[int] = None,
    item_ref: Optional[str] = None,
) -> float:
    """Score 0.0–10.0. Non-scientific assets always score 0.0. Native tables score at least 2."""
    # Non-scientific assets receive a hard 0 so they are never auto-selected.
    if classification in _NON_SCIENTIFIC_CLASSES:
        return 0.0
    if _is_decorative(caption, page_number, item_ref):
        return 0.0

    combined = " ".join(filter(None, [caption, section_name] + context_texts)).lower()

    score = sum(pts for kw, pts in _SCORE_MAP.items() if kw in combined)

    if section_name:
        sec = section_name.lower()
        if any(s in sec for s in _HIGH_SECTIONS):
            score += 1
        elif any(s in sec for s in _LOW_SECTIONS):
            score -= 1

    if asset_type == "native_table":
        score = max(score, 2.0)

    return max(0.0, round(min(score, 10.0), 1))


def classify_figure(
    image_path: Optional[str],
    csv_path: Optional[str],
    csv_rows: Optional[int],
    csv_cols: Optional[int],
    caption: Optional[str],
    conversion_status: Optional[str],
    page_number: Optional[int] = None,
    item_ref: Optional[str] = None,
) -> str:
    """
    Return figure classification string.

    Priority order:
      1. Decorative / logo / license detection (always wins)
      2. Successful PP-Chart2Table conversion → chart / multi_panel_figure
      3. Caption pattern matching
      4. Conversion outcome inference
    """
    if not image_path:
        return "unknown"

    # ── Priority 1: Non-scientific detection ─────────────────────────────────
    decorative = _is_decorative(caption, page_number, item_ref)
    if decorative:
        return decorative

    cap = (caption or "").lower()

    if _LOGO_PATTERNS.search(cap):
        return "publisher_logo"
    if _LICENSE_PATTERNS.search(cap):
        return "license_icon"

    # ── Priority 2: Successful chart conversion ───────────────────────────────
    if csv_path and conversion_status == "complete" and csv_rows and csv_rows >= 2:
        if csv_cols and csv_cols > 12:
            return "multi_panel_figure"
        return "chart"

    # ── Priority 3: Caption-based classification ─────────────────────────────
    if _PANEL_CAPTIONS.search(cap):
        return "multi_panel_figure"
    if _CHEMICAL_CAPTIONS.search(cap):
        return "chemical_structure"
    if _DIAGRAM_CAPTIONS.search(cap):
        return "diagram"
    if _CHART_CAPTIONS.search(cap):
        return "chart"

    # ── Priority 4: Infer from conversion outcome ─────────────────────────────
    if conversion_status == "not_a_chart":
        return "photograph"
    if conversion_status in ("failed", "skipped"):
        return "unknown"

    return "unknown"
