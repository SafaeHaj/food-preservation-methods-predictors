"""Grading provenance: confidence is computed here and nowhere else.

The previous pipeline asked the model to score its own confidence, which is a number with
no referent — a model that invents a value invents a confidence for it too. Here the
question is testable instead: is the quote actually present in the item the span cites?

That tops the scale, and everything else is placed by distance from it:

    1.0  stated, and the quote is in the cited item
    0.5  stated, but unquoted or the quote is not there
    0.7  derived from operands the paper supplies
    0.3  inferred on weaker grounds
    0.0  the cited ref resolves to nothing the model was shown

with a 0.6 multiplier on anything read off a chart, because a value taken from a plotted
line is an estimate however confidently it is stated.
"""

from __future__ import annotations

import re
from itertools import chain

from shared.schemas.science import GoldBundle

#: Two rungs for `stated`: a quote that checks out, and one that does not.
STATED_VERBATIM, STATED_UNQUOTED = 1.0, 0.5
METHOD_SCORES = {"derived": 0.7, "inferred": 0.3}
CHART_READING_PENALTY = 0.6

_WHITESPACE = re.compile(r"\s+")


def searchable(text) -> str:
    """Case- and whitespace-folded, so a quote is not failed for rewrapped lines."""
    return _WHITESPACE.sub(" ", str(text or "")).strip().lower()


def reference_text_index(package: dict) -> dict:
    """{docling_item_ref: searchable text} over exactly the items the prompt shows.

    Built from what the model was given, not from the whole document: a ref that fails to
    resolve here is one it was never shown, which is the difference between a quote that
    could not be checked and a citation that was invented.
    """
    index = {}
    for section in package.get("sections", []):
        ref = section.get("docling_item_ref")
        if ref:
            index[ref] = searchable(
                f"{section.get('section_title', '')}\n{section.get('content_markdown', '')}")
    for asset in chain(package.get("tables", []), package.get("references", []),
                       package.get("figures", [])):
        ref = asset.get("docling_item_ref")
        if not ref:
            continue
        parts = [asset.get("caption") or "", asset.get("context_markdown") or "",
                 asset.get("preview_markdown") or ""]
        parts += [f"{item.get('column_label')} {item.get('row_labels')} "
                  f"{item.get('axis_value')} {item.get('value')}"
                  for item in asset.get("observations", [])]
        index[ref] = searchable("\n".join(parts))
    return index


def score_evidence(span, index: dict) -> float:
    """Grade one span against the text it cites."""
    resolved = index.get(span.docling_item_ref)
    if resolved is None:
        return 0.0
    if span.method == "stated":
        quote = searchable(span.exact_text)
        score = STATED_VERBATIM if quote and quote in resolved else STATED_UNQUOTED
    else:
        score = METHOD_SCORES[span.method]
    if span.value_is_approximate or span.source_type == "figure":
        score *= CHART_READING_PENALTY
    return round(score, 3)


def score_bundle(bundle: GoldBundle, index: dict) -> GoldBundle:
    """Overwrite every span's confidence with a computed one. Mutates, and returns."""
    for record in bundle.experiments:
        for span in record.evidence:
            span.confidence = score_evidence(span, index)
    return bundle
