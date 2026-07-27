"""Which assets get sent to the LLM.

This policy existed twice: once in `get_evidence_packages` (which told the user what would
be sent) and once in `_run_llm_validation` (which decided what actually was sent). They
were written separately, so the preview and the reality could disagree -- the preview
treated an explicit selection as overriding, the job treated it as short-circuiting, and
the "no relevant evidence" fallbacks differed. One implementation, consulted by both, is
the only way the preview can be trusted.

Thresholds come from `ExtractionSettings` rather than module literals.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from shared.config import get_extraction_settings
from shared.db.models import ExtractionAsset

_settings = get_extraction_settings()

TEXT_LINK_TYPES = frozenset(
    {"neighbor_before", "neighbor_after", "keyword_match", "same_section",
     "explicit_figure_reference"}
)


@dataclass(frozen=True)
class SelectionVerdict:
    """Why one asset is in or out, in terms the UI can show the user verbatim."""

    include: bool
    is_decorative: bool
    auto_include: bool
    auto_reason: Optional[str] = None
    exclude_reason: Optional[str] = None


def _has_csv(asset: ExtractionAsset) -> bool:
    return bool(asset.csv_path and Path(asset.csv_path).exists())


def judge(asset: ExtractionAsset) -> SelectionVerdict:
    """Decide whether `asset` belongs in the LLM evidence package."""
    if asset.classification in _settings.NON_SCIENTIFIC_CLASSIFICATIONS:
        return SelectionVerdict(
            include=False,
            is_decorative=True,
            auto_include=False,
            exclude_reason=f"decorative/non-scientific ({asset.classification})",
        )

    score = asset.relevance_score or 0.0
    auto_include = False
    auto_reason: Optional[str] = None

    # Native tables clear a lower bar than figures: a table is dense structured data even
    # when the surrounding text gives it a weak relevance score.
    if asset.asset_type == "native_table" and score >= _settings.AUTO_SELECT_MIN_TABLE_SCORE:
        auto_include, auto_reason = True, f"native table (relevance {score:.1f})"
    elif asset.classification == "chart" and _has_csv(asset):
        auto_include, auto_reason = True, "chart CSV available"
    elif score >= _settings.AUTO_SELECT_MIN_SCORE:
        auto_include, auto_reason = True, f"relevance score {score:.1f}"

    include = bool(asset.selected_for_llm) or auto_include
    return SelectionVerdict(
        include=include,
        is_decorative=False,
        auto_include=auto_include,
        auto_reason=auto_reason,
        exclude_reason=None if include else "low relevance score — not auto-selected",
    )


def select_for_llm(assets: list[ExtractionAsset]) -> list[ExtractionAsset]:
    """The assets to send, with a last-resort fallback.

    If the policy selects nothing, fall back to every non-decorative asset: an extraction
    that sends nothing produces a job that "succeeds" with zero results, which reads to the
    user as a silent failure.
    """
    selected = [asset for asset in assets if judge(asset).include]
    if selected:
        return selected
    return [asset for asset in assets if not judge(asset).is_decorative]
