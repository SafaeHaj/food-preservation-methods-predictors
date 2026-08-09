"""Asking the model which column is the axis — the first of the pipeline's two LLM calls.

The gate rejects a table when it cannot find the column that orders the rows. Often the
column is there and holds text ("control, 6 days") rather than plain numbers, which is
exactly what a language model reads well and a structural test does not.

So the model is asked for *a column name*, never a value. Its answer is fed back into the
gate, which re-reads the table and extracts every number itself. A wrong hint therefore
costs a table that was already failing; it cannot introduce a number the paper never
printed.

Failure here is non-fatal by contract: no provider, a bad reply, a timeout — the assets
stay in `review`, the gate report says so, and the paper still reaches Gold. That is what
lets the whole pipeline run deterministically with no model configured at all.
"""

from __future__ import annotations

import json
import logging
from itertools import chain

from pydantic import ValidationError

from shared.schemas.science import AssetHint, ReviewReply

from shared.science.gate import (
    canonical_key, column_label, fits_schema, observation_payload,
)

from app.services import timings
from app.services.llm import LLMBadResponse, LLMPromptTooLarge, LLMUnavailable

logger = logging.getLogger(__name__)

REVIEW_SYSTEM_PROMPT = """\
You are reading tables and charts recovered from one scientific paper.

Each asset below has numbers in it, but the software could not tell which column orders
the rows into a series. Name that column. Do NOT transcribe any values.

For each asset return one object:

{
  "docling_item_ref": REQUIRED - copy it from the asset,
  "axis_column": the exact name, copied from this asset's `columns`, of the column whose
                 cells carry the point each row was observed at - a storage day, a
                 concentration, a time. The cell may hold more than that, as in
                 "control, 6 days"; name it anyway. Use null if no column does.
  "not_a_series": true when this is not repeated measurements at all - a composition
                  breakdown, a list of equipment, a statistics summary - else false,
  "why": one short sentence
}

Rules:
  * `axis_column` must be copied verbatim from that asset's `columns`, or be null. An
    invented name is discarded. An unheaded column is listed as "row label"; that is a
    name you may use.
  * A column of measured quantities is NOT the axis. The axis is what those quantities
    were measured against, and it is a column of text here - if it were a column of plain
    numbers the software would already have found it.
  * If several columns could be it, pick the one whose values repeat across groups.

Return ONLY valid JSON: {"assets": [ ... ]}
"""


def build_prompt(package: dict) -> str:
    return json.dumps({
        "paper_slug": package["paper_slug"],
        "assets": [{
            "docling_item_ref": asset.get("docling_item_ref"),
            "kind": "figure" if asset.get("is_figure") else "table",
            "caption": asset.get("caption"),
            "columns": [column_label(name) for name in asset.get("headers", [])],
            "why_unresolved": asset.get("why"),
            "preview": asset.get("preview_markdown"),
        } for asset in package.get("review", [])],
    }, ensure_ascii=False, indent=2, default=str)


def _hints(payload: dict) -> dict[str, AssetHint]:
    try:
        reply = ReviewReply.model_validate(payload)
    except ValidationError:
        # Salvage what parses: one malformed entry should not discard the other nine.
        hints = {}
        for entry in payload.get("assets") or []:
            try:
                hint = AssetHint.model_validate(entry)
            except ValidationError:
                continue
            hints[hint.docling_item_ref] = hint
        return hints
    return {hint.docling_item_ref: hint for hint in reply.assets}


def adjudicate(package: dict, client) -> int:
    """Ask which column is the axis, re-gate with the answer, return how many that promoted.

    An asset whose hint does not make the table fit stays in `review` carrying what the
    model said, so a bad hint is legible in the gate report rather than silent.
    """
    review = package.get("review") or []
    if not review or client is None:
        return 0

    slug = package["paper_slug"]
    try:
        with timings.stage_timer("review", slug, assets=len(review)):
            result = client.json_completion(
                system_prompt=REVIEW_SYSTEM_PROMPT,
                user_prompt=build_prompt(package),
                schema=ReviewReply.model_json_schema(),
                cache_scope="review",
                paper=slug,
            )
    except (LLMUnavailable, LLMBadResponse, LLMPromptTooLarge) as exc:
        logger.info("Review adjudication unavailable for %s (%s); assets stay unresolved",
                    slug, exc)
        return 0

    hints = _hints(result.payload)
    promoted, still_open = 0, []
    for asset in review:
        hint = hints.get(asset.get("docling_item_ref"))
        headers = [str(name) for name in asset.get("headers", [])]
        named = {column_label(name) for name in headers}

        if hint is None or hint.not_a_series or not hint.axis_column:
            asset["hint"] = "not a series" if (hint and hint.not_a_series) else "no answer"
            asset["why"] = (hint.why if hint else None) or asset.get("why")
            still_open.append(asset)
            continue
        if hint.axis_column not in named:
            asset["hint"] = f"named a column that is not there: {hint.axis_column!r}"
            still_open.append(asset)
            continue

        fit = fits_schema(headers, asset.get("rows") or [],
                          prefer_axis=canonical_key(hint.axis_column))
        if not fit.fits or fit.orientation != "keyed":
            asset["hint"] = (f"{hint.axis_column!r} does not key the rows "
                             f"({fit.reason if not fit.fits else fit.orientation + ' fit'})")
            still_open.append(asset)
            continue

        asset["gate"] = fit.summary()
        asset["observations"] = observation_payload(fit)
        asset["hint"] = f"axis named by the model: {hint.axis_column!r}"
        # The raw rows were kept only so the table could be re-gated; drop them now that
        # it has been, or every promoted asset carries a second copy of its own data.
        asset.pop("rows", None)
        (package["figures"] if asset.get("is_figure") else package["tables"]).append(asset)
        promoted += 1

    package["review"] = still_open
    report = package.setdefault("gate_report", {})
    report["review"] = len(still_open)
    report["review_promoted"] = promoted
    report["tables_accepted"] = len(package.get("tables", []))
    report["figures_accepted"] = len(package.get("figures", []))
    report["observations"] = sum(
        len(item.get("observations") or [])
        for item in chain(package.get("tables", []), package.get("figures", [])))

    logger.info("Review for %s: %d of %d assets keyed by the model",
                slug, promoted, promoted + len(still_open))
    return promoted
