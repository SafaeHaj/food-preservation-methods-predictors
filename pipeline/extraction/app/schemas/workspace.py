"""Extraction workspace response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class AssetLinks(BaseModel):
    """Pre-signed URLs for an asset's binaries.

    The client no longer builds these itself. It could not sign them, and building them
    client-side is what forced the gateway to accept unauthenticated `/image` and `/csv`
    requests in the first place. Null means the file does not exist for this asset.
    """

    image: Optional[str] = None
    page_image: Optional[str] = None
    csv: Optional[str] = None


class ContextLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    link_type: str
    text: str
    item_ref: Optional[str] = None
    page_number: Optional[int] = None
    score: float = 0.0


class AssetOut(BaseModel):
    id: int
    paper_id: int
    project_id: int
    docling_item_ref: Optional[str] = None
    asset_type: str
    page_number: Optional[int] = None
    bbox: Optional[dict[str, Any]] = None
    section_name: Optional[str] = None
    caption: Optional[str] = None
    classification: str
    conversion_status: Optional[str] = None
    conversion_error: Optional[str] = None
    relevance_score: float = 0.0
    selected_for_llm: bool = False
    user_note: Optional[str] = None
    csv_rows: Optional[int] = None
    csv_cols: Optional[int] = None
    has_image: bool = False
    has_page_image: bool = False
    has_csv: bool = False
    links: AssetLinks = AssetLinks()
    paper_name: Optional[str] = None
    created_at: Optional[datetime] = None


class AssetDetailOut(AssetOut):
    context_links: list[ContextLinkOut] = []


class AssetPage(BaseModel):
    total: int
    items: list[AssetOut]


class AssetUpdate(BaseModel):
    """Only the three fields a curator may change. Previously a bare `dict` body, so any
    key could be written and none were validated."""

    selected_for_llm: Optional[bool] = None
    classification: Optional[str] = None
    user_note: Optional[str] = None


class JobAccepted(BaseModel):
    """The only thing a "start work" endpoint returns.

    Progress is followed through `GET /api/jobs/{job_id}/events`, so there is no per-workflow
    status endpoint and no reason to return a snapshot that is stale on arrival.
    """

    job_id: int
    status: str


class EvidenceAssetOut(AssetDetailOut):
    """An asset annotated with why it was or was not selected for the LLM."""

    link_count: int = 0
    auto_include: bool = False
    auto_reason: Optional[str] = None
    is_decorative: bool = False
    effective_include: bool = False
    exclude_reason: Optional[str] = None


class ParagraphOut(BaseModel):
    asset_id: int
    link_id: int
    link_type: str
    text: str
    page_number: Optional[int] = None
    score: float = 0.0
    section_name: Optional[str] = None
    asset_caption: Optional[str] = None
    relevance_score: float = 0.0
    auto_reason: Optional[str] = None


class EvidenceTotals(BaseModel):
    paragraphs: int
    native_tables: int
    chart_csvs: int
    excluded: int


class EvidencePackagesOut(BaseModel):
    paragraphs: list[ParagraphOut]
    native_tables: list[EvidenceAssetOut]
    chart_csvs: list[EvidenceAssetOut]
    excluded: list[EvidenceAssetOut]
    totals: EvidenceTotals
    chart_conversion_available: bool
    chart_conversion_error: Optional[str] = None


class GateDecisionOut(BaseModel):
    """One asset's structural verdict.

    `verdict` is accepted | reference | review | rejected, and `why` says which test it
    failed — a rejected table that reads "no column orders the rows like an axis" is a
    different problem from one that reads "cells under the axis columns are not numeric".
    """

    kind: str
    index: Optional[int] = None
    docling_item_ref: Optional[str] = None
    page_number: Optional[int] = None
    caption: Optional[str] = None
    verdict: str
    why: Optional[str] = None
    stage: Optional[str] = None
    axis_label: Optional[str] = None
    axis_points: list[Any] = []
    observation_count: int = 0


class GateReportOut(BaseModel):
    #: Empty until the workspace pipeline has run; the counts are then its summary.
    available: bool = False
    totals: dict[str, Any] = {}
    decisions: list[GateDecisionOut] = []
