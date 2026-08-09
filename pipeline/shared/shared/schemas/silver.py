"""The Silver package: what extraction hands processing for one paper.

Extraction stages this on the shared uploads volume and records its path on
`DoclingCache.silver_package_path`; processing reads it by that pointer. Both containers
mount the same volume, so serialising megabytes of observations through an HTTP response
would buy nothing and would make ingestion fail whenever the extraction API was down, even
though the data is sitting on disk.

The real risk of a file is coupling on an untyped JSON shape, so the shape is typed here,
in `shared`, owned by neither service. The producer validates before writing — a package the
consumer could not read fails in the extraction job, where the paper and the stage are on
screen — and the consumer refuses an unknown `package_version` with a message naming the
fix, rather than raising a `KeyError` three modules deep in normalisation.

Bump `PACKAGE_VERSION` on any change that is not additive-and-optional. Both services must
then be redeployed together; that cost is deliberate and is the price of the guarantee.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "PACKAGE_VERSION", "Observation", "GateSummary", "PlotProbeSummary", "GatedAsset",
    "SectionPayload", "TextItem", "GateReport", "SilverPackage",
]

PACKAGE_VERSION = "silver-1"


class Observation(BaseModel):
    """One value at one axis point, with its labels still unresolved.

    Naming happens in processing's vocabulary, not here — which is what lets the gate stay
    free of any corpus-specific term.
    """

    model_config = ConfigDict(extra="forbid")
    axis_value: float
    value: float
    column_label: Optional[str] = None
    row_labels: dict[str, str] = Field(default_factory=dict)
    reports_mean: bool = False


class GateSummary(BaseModel):
    """The structural verdict on one asset: what the gate found and why it decided so."""

    model_config = ConfigDict(extra="forbid")
    fits: Optional[bool] = None
    reason: str = ""
    orientation: Optional[str] = None
    axis_label: Optional[str] = None
    axis_points: list[Any] = Field(default_factory=list)
    axis_confidence: float = 0.0
    axis_runs: int = 0
    value_columns: list[str] = Field(default_factory=list)
    label_columns: list[str] = Field(default_factory=list)
    observation_count: int = 0


class PlotProbeSummary(BaseModel):
    """The geometry probe's verdict on a figure, kept so a corpus-wide miss is legible."""

    model_config = ConfigDict(extra="forbid")
    plot_like: bool = False
    reason: str = ""
    width: int = 0
    height: int = 0
    background_fraction: float = 0.0
    ink_fraction: float = 0.0
    distinct_colours: int = 0
    h_rule: float = 0.0
    v_rule: float = 0.0
    axis_aligned_edges: float = 0.0
    #: From the caption together with the prose around it — what FIGURE_CAPTION_FILTER
    #: reads. Broad on purpose: it is answering "is this a photograph?".
    caption_verdict: str = "unknown"
    #: From the figure's own caption alone — what FIGURE_REQUIRE_PLOT_CAPTION reads, and
    #: the stricter of the two, since surrounding prose calls almost anything a plot.
    own_caption_verdict: str = "unknown"


class GatedAsset(BaseModel):
    """One table or figure and what the gate did with it.

    The only `extra="allow"` model here: each verdict legitimately carries its own extras
    (a rejected asset has `stage`, a reviewed one keeps `rows` so it can be re-gated, a
    converted figure has `conversion_status`), and forbidding them would mean four
    near-identical models for one concept.
    """

    model_config = ConfigDict(extra="allow")
    docling_item_ref: Optional[str] = None
    kind: Optional[str] = None
    index: Optional[int] = None
    caption: Optional[str] = None
    page_number: Optional[int] = None
    order: int = 0
    is_figure: bool = False
    headers: list[Any] = Field(default_factory=list)
    #: Kept only on a `review` asset, so the gate can re-read it once a model names the
    #: axis. Dropped on promotion — otherwise every promoted asset carries its data twice.
    rows: Optional[list[list[Any]]] = None
    observations: list[Observation] = Field(default_factory=list)
    gate: GateSummary = Field(default_factory=GateSummary)
    probe: Optional[PlotProbeSummary] = None
    preview_markdown: Optional[str] = None
    context_markdown: Optional[str] = None
    context_refs: list[str] = Field(default_factory=list)
    section_hint: Optional[str] = None
    csv_path: Optional[str] = None
    cleaned_csv_path: Optional[str] = None
    image_path: Optional[str] = None
    #: Why this asset is where it is: the gate's reason, the stage that rejected it, or
    #: what the review model said about it.
    why: Optional[str] = None
    stage: Optional[str] = None
    reason: Optional[str] = None
    hint: Optional[str] = None


class SectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section_title: str
    content_markdown: str
    docling_item_ref: Optional[str] = None
    page_number: Optional[int] = None
    level: int = 1
    item_refs: list[str] = Field(default_factory=list)


class TextItem(BaseModel):
    """One text item in reading order — what `local_context` ranks against."""

    model_config = ConfigDict(extra="forbid")
    docling_item_ref: str
    text: str
    page_number: Optional[int] = None
    order: int = 0
    is_heading: bool = False
    level: int = 1
    heading: Optional[str] = None


class GateReport(BaseModel):
    """The counts that say whether a paper yielded what it should have."""

    model_config = ConfigDict(extra="forbid")
    tables_in: int = 0
    tables_accepted: int = 0
    figures_in: int = 0
    #: Figures the probe let through to the chart model. `figures_in` minus this is what
    #: the probe's filters saved, which is the whole cost story on a CPU run.
    figures_converted: int = 0
    figures_accepted: int = 0
    #: {"plot"|"photo"|"unknown": count} over every figure's own caption.
    caption_verdicts: dict[str, int] = Field(default_factory=dict)
    rejected_by_stage: dict[str, int] = Field(default_factory=dict)
    references: int = 0
    review: int = 0
    review_promoted: int = 0
    observations: int = 0


class SilverPackage(BaseModel):
    """Everything extraction knows about one paper, with nothing yet named."""

    model_config = ConfigDict(extra="forbid")
    package_version: str = PACKAGE_VERSION
    cache_key: str
    paper_slug: str
    file_hash: str
    cache_dir: str
    markdown_path: str = ""
    page_count: int = 0
    source_name: Optional[str] = None

    sections: list[SectionPayload] = Field(default_factory=list)
    section_source: str = ""
    methods_refs: list[str] = Field(default_factory=list)
    texts: list[TextItem] = Field(default_factory=list)

    tables: list[GatedAsset] = Field(default_factory=list)
    figures: list[GatedAsset] = Field(default_factory=list)
    references: list[GatedAsset] = Field(default_factory=list)
    review: list[GatedAsset] = Field(default_factory=list)
    rejected: list[GatedAsset] = Field(default_factory=list)

    gate_report: GateReport = Field(default_factory=GateReport)
