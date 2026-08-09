"""The paper's prose: segmented into sections, indexed by position.

Two things need it. Gold's prompt is built from the methods section, and every figure
carries the text nearest to it so interpretation can tell which indicator a chart plots.

Context is chosen by *position* — the same page first, then reading order — never by
keyword. That is the same discipline as the schema gate: a keyword list tuned on this
corpus would quietly stop working on the next one.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from shared.config import get_extraction_settings

_settings = get_extraction_settings()

PREAMBLE_TITLE = "Document"

_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+(.*)$")

_METHODS_HEAD = re.compile(
    r"materials?\s*(?:and|&)\s*methods?|methods?\s*(?:and|&)\s*materials?"
    r"|^\s*\d*\.?\s*(?:methods?|methodolog\w*|experimental)\b"
    r"|sample\s+(?:preparation|processing)|preparation\s+of\b", re.IGNORECASE)
_METHODS_STOP = re.compile(
    r"^\s*\d*\.?\s*(?:results?|discussion|conclusion|acknowledg\w*|references|bibliography)\b",
    re.IGNORECASE)


def _text_items(result) -> list[dict]:
    """`DoclingText` objects as the plain dicts every function below reads.

    Silver takes dicts rather than the dataclass so the same code runs against a cached
    manifest, a fixture and a live parse without three call signatures.
    """
    return [
        {
            "docling_item_ref": item.item_ref,
            "page_number": item.page_number,
            "text": item.text,
            "heading": item.heading_context,
            "is_heading": item.is_heading,
            "level": item.level,
            "order": item.order,
        }
        for item in result.texts
    ]


def markdown_sections(markdown_text: str) -> list:
    """Fallback segmentation from the exported markdown, when no item is a heading."""
    sections = []
    title, lines = PREAMBLE_TITLE, []

    def close():
        if lines:
            sections.append({"section_title": title,
                             "content_markdown": "\n".join(lines).strip()})

    for line in markdown_text.splitlines():
        heading = _MARKDOWN_HEADING.match(line.strip())
        if not heading:
            lines.append(line)
            continue
        close()
        title, lines = heading.group(1).strip(), []
    close()

    kept = [section for section in sections if section["content_markdown"]]
    for order, section in enumerate(kept):
        section["docling_item_ref"] = f"#/sections/{order}"
        section["page_number"] = None
        section["level"] = 1
        section["item_refs"] = []
    return kept


def document_sections(texts: Sequence[dict]) -> list:
    """Segment on the heading items themselves, keeping each section's member refs.

    Preferred over the markdown route because it preserves the anchor a `prose` evidence
    span cites: a section here has a real `docling_item_ref`, and the refs of every
    paragraph inside it.
    """
    sections, current = [], None

    def open_section(item):
        return {"section_title": (item or {}).get("text") or PREAMBLE_TITLE,
                "docling_item_ref": (item or {}).get("docling_item_ref"),
                "page_number": (item or {}).get("page_number"),
                "level": (item or {}).get("level") or 1,
                "item_refs": [], "lines": []}

    for item in texts:
        if item.get("is_heading"):
            if current is not None:
                sections.append(current)
            current = open_section(item)
            continue
        if current is None:
            current = open_section(None)
        current["item_refs"].append(item["docling_item_ref"])
        current["lines"].append(item["text"])
        if current["page_number"] is None:
            current["page_number"] = item.get("page_number")
    if current is not None:
        sections.append(current)

    kept = []
    for order, section in enumerate(sections):
        content = "\n\n".join(section.pop("lines")).strip()
        if not content:
            continue
        kept.append({**section, "content_markdown": content,
                     "docling_item_ref": section["docling_item_ref"] or f"#/sections/{order}"})
    return kept


def paper_sections(result) -> tuple:
    """(sections, how they were found). Heading items when there are any, markdown else."""
    texts = _text_items(result)
    if any(item["is_heading"] for item in texts):
        return document_sections(texts), "docling items"

    markdown_path = Path(result.markdown_path)
    if not markdown_path.exists():
        return [], "none"
    return markdown_sections(markdown_path.read_text(encoding="utf-8")), "markdown headings"


def methods_section_refs(sections: Sequence[dict]) -> set:
    """Refs of the methods section and its subsections.

    Ends at the first sibling-or-shallower heading in a nested document, or at a heading
    that names a later section in a flat one. Nesting is only trusted when the document
    actually has more than one level -- otherwise every heading looks like a sibling and
    the methods would end at their own first paragraph.
    """
    nested = len({section.get("level") or 1 for section in sections}) > 1
    found, head_level = set(), None
    for section in sections:
        title = section.get("section_title") or ""
        level = section.get("level") or 1
        if head_level is None:
            if _METHODS_HEAD.search(title):
                head_level = level
                found.add(section["docling_item_ref"])
            continue
        if _METHODS_STOP.search(title) or (nested and level <= head_level):
            break
        found.add(section["docling_item_ref"])
    return found


def build_text_index(result) -> dict:
    """Bucket the paper's text items by page, once, for every asset to share."""
    texts = _text_items(result)
    by_page: dict = {}
    for item in texts:
        by_page.setdefault(item.get("page_number"), []).append(item)
    return {"all": texts, "by_page": by_page, "context": {}}


def local_context(text_index: dict, anchor: dict, budget: int | None = None) -> dict:
    """Text near an asset, chosen by position: the page first, then reading order for a
    page that is all figure.

    Memoised per anchor — the probe and the gated record both want the same passage, and
    ranking every text item twice per asset is pure CPU spent while the GPU waits.
    """
    budget = _settings.FIGURE_CONTEXT_CHARS if budget is None else budget
    cache = text_index.setdefault("context", {})
    order = anchor.get("order", 0)
    page = anchor.get("page_number")
    key = (anchor.get("docling_item_ref"), order, page, budget)
    hit = cache.get(key)
    if hit is not None:
        return hit

    candidates = text_index["by_page"].get(page) if page is not None else None
    if not candidates:
        candidates = text_index["all"]

    ranked = sorted(candidates, key=lambda item: abs(item.get("order", 0) - order))
    chosen, used = [], 0
    for item in ranked:
        text = item.get("text", "")
        if used + len(text) > budget and chosen:
            break
        chosen.append(item)
        used += len(text)
    chosen.sort(key=lambda item: item.get("order", 0))
    headings = [item.get("heading") for item in chosen if item.get("heading")]
    context = {
        "context_markdown": "\n\n".join(item["text"] for item in chosen),
        "context_refs": [item["docling_item_ref"] for item in chosen],
        "section_hint": headings[0] if headings else None,
    }
    cache[key] = context
    return context
