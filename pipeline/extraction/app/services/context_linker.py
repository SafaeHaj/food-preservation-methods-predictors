"""
context_linker.py — Deterministic context linking for figures and tables.

For each visual asset, builds typed context links at four levels:
  1. caption          : figure / table caption text
  2. neighbor_before  : text element immediately preceding the asset
  3. neighbor_after   : text element immediately following the asset
  4. explicit_ref     : paragraphs that mention "Figure N" / "Table N" explicitly
  5. keyword_match    : same-section text containing scientific keywords from the caption

No LLM is involved — all linking is deterministic and testable.
"""
import logging
import re
from typing import Optional

from app.services.docling_extractor import DoclingResult

logger = logging.getLogger(__name__)

_SCIENTIFIC_KW = frozenset({
    "cfu", "log cfu", "tvc", "total viable", "aerobic", "yeast", "mold",
    "mould", "coliform", "salmonella", "listeria", "staphylococcus",
    "lactic acid", "ph", "tbars", "tvb-n", "tvb", "water activity", "aw",
    "oxidation", "peroxide", "color", "colour", "texture", "firmness",
    "hardness", "chitosan", "nisin", "thymol", "rosemary", "oregano",
    "thyme", "essential oil", "bacteriocin", "antimicrobial", "antioxidant",
    "control", "treatment", "coating", "dip", "spray", "concentration",
    "day", "storage", "shelf life", "shelf-life",
    "beef", "chicken", "pork", "lamb", "fish", "salmon", "fillet",
    "sausage", "minced", "ground", "cheese", "milk", "whey", "casein",
    "significant", "p<", "mean", "±",
})

_STOP_WORDS = frozenset({
    "with", "from", "that", "this", "during", "after", "before",
    "their", "were", "have", "been", "when", "also", "than",
})


def _sorted_elements(docling_result: DoclingResult) -> list:
    """Flat list of all elements sorted by page then type (text first)."""
    elements = []
    for t in docling_result.texts:
        elements.append({"type": "text", "item": t, "page": t.page_number})
    for t in docling_result.tables:
        elements.append({"type": "table", "item": t, "page": t.page_number})
    for f in docling_result.figures:
        elements.append({"type": "figure", "item": f, "page": f.page_number})
    elements.sort(key=lambda e: (e["page"], {"text": 0, "table": 1, "figure": 2}[e["type"]]))
    return elements


def _figure_label(caption: Optional[str], item_ref: str, idx: int) -> Optional[str]:
    """Extract the explicit label like 'Figure 3' or 'Table 2' from caption."""
    if caption:
        m = re.search(r'\b(figure|fig\.?|table|tbl\.?)\s*(\d+[a-z]?)', caption, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    if "pictures" in item_ref or "figures" in item_ref:
        return f"figure {idx + 1}"
    if "tables" in item_ref:
        return f"table {idx + 1}"
    return None


def build_context_links(
    docling_result: DoclingResult,
    item_ref: str,
    asset_type: str,
    page_number: int,
    caption: Optional[str],
    asset_index: int,
    max_links: int = 20,
) -> list:
    """
    Return context link dicts for one asset.
    Each dict: {link_type, text, item_ref, page_number, score}.
    """
    links: list = []

    # ── Level 1: Caption ──────────────────────────────────────────────────────
    if caption and caption.strip():
        links.append({
            "link_type": "caption",
            "text": caption.strip(),
            "item_ref": item_ref,
            "page_number": page_number,
            "score": 1.0,
        })

    # ── Build sorted element list ──────────────────────────────────────────────
    all_elems = _sorted_elements(docling_result)
    asset_pos = next(
        (i for i, e in enumerate(all_elems) if e["item"].item_ref == item_ref),
        None,
    )

    if asset_pos is not None:
        # ── Level 2: Neighbors ────────────────────────────────────────────────
        for j in range(asset_pos - 1, max(0, asset_pos - 8), -1):
            if all_elems[j]["type"] == "text" and all_elems[j]["item"].text.strip():
                t = all_elems[j]["item"]
                links.append({
                    "link_type": "neighbor_before",
                    "text": t.text.strip()[:2000],
                    "item_ref": t.item_ref,
                    "page_number": t.page_number,
                    "score": 0.9,
                })
                break

        for j in range(asset_pos + 1, min(len(all_elems), asset_pos + 8)):
            if all_elems[j]["type"] == "text" and all_elems[j]["item"].text.strip():
                t = all_elems[j]["item"]
                links.append({
                    "link_type": "neighbor_after",
                    "text": t.text.strip()[:2000],
                    "item_ref": t.item_ref,
                    "page_number": t.page_number,
                    "score": 0.9,
                })
                break

    # ── Level 3: Explicit figure/table references ─────────────────────────────
    label = _figure_label(caption, item_ref, asset_index)
    if label:
        label_lo = label.lower()
        # Build regex patterns: "Figure 3", "Fig. 3", "Fig 3", etc.
        parts = label_lo.split()
        num_part = parts[-1] if parts else ""
        patterns = [
            re.compile(rf'\b(figure|fig\.?)\s*{re.escape(num_part)}\b', re.IGNORECASE),
            re.compile(rf'\b(table|tbl\.?)\s*{re.escape(num_part)}\b', re.IGNORECASE),
        ]
        seen_refs: set = set()
        for t in docling_result.texts:
            if t.item_ref == item_ref or t.item_ref in seen_refs:
                continue
            for pat in patterns:
                if pat.search(t.text):
                    links.append({
                        "link_type": "explicit_figure_reference",
                        "text": t.text.strip()[:2000],
                        "item_ref": t.item_ref,
                        "page_number": t.page_number,
                        "score": 0.85,
                    })
                    seen_refs.add(t.item_ref)
                    break
            if len(seen_refs) >= 6:
                break

    # ── Level 4: Same-section keyword match ───────────────────────────────────
    # Determine section heading for this asset
    asset_section: Optional[str] = None
    for t in docling_result.texts:
        if t.heading_context and t.page_number == page_number:
            asset_section = t.heading_context
            break

    # Caption-derived keywords for targeted matching
    cap_kws: set = set()
    if caption:
        words = re.findall(r'\b[a-zA-Z]{4,}\b', caption.lower())
        cap_kws = {w for w in words if w not in _STOP_WORDS}

    if asset_section:
        kw_hits = 0
        for t in docling_result.texts:
            if t.heading_context != asset_section or t.item_ref == item_ref:
                continue
            tlo = t.text.lower()
            has_sci = any(kw in tlo for kw in _SCIENTIFIC_KW)
            has_cap = any(cw in tlo for cw in cap_kws if len(cw) > 3)
            if has_sci or has_cap:
                links.append({
                    "link_type": "keyword_match",
                    "text": t.text.strip()[:2000],
                    "item_ref": t.item_ref,
                    "page_number": t.page_number,
                    "score": 0.6,
                })
                kw_hits += 1
                if kw_hits >= 5:
                    break

    # ── Deduplicate by (item_ref, link_type), keep highest score ─────────────
    best: dict = {}
    for link in links:
        key = f"{link.get('item_ref', '')}::{link['link_type']}"
        if key not in best or link["score"] > best[key]["score"]:
            best[key] = link

    # ── Quality filter: reject fragments that are too short or malformed ──────
    MIN_TEXT_CHARS = 50  # anything shorter is a heading, fragment, or isolated word
    filtered: list = []
    for link in best.values():
        text = link.get("text", "").strip()
        # Always keep captions regardless of length
        if link["link_type"] == "caption":
            filtered.append(link)
            continue
        # Reject very short fragments
        if len(text) < MIN_TEXT_CHARS:
            continue
        # Reject fragments that look like page headers/footers:
        # all-caps short lines, page number only, URL-only lines
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if len(lines) == 1:
            sole = lines[0]
            if re.match(r'^[A-Z\s\-\.]{2,30}$', sole):  # all-caps header
                continue
            if re.match(r'^\d{1,4}$', sole):  # page number only
                continue
        filtered.append(link)

    return filtered[:max_links]
