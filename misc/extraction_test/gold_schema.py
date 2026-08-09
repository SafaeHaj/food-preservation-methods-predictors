"""The extraction schema: the controlled values every record is checked against, and the
Pydantic models Gold assembles. Kept out of the notebook so the pipeline, the services and
any consumer validate against one definition rather than a copy each.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "INDICATOR_TYPES", "FUNCTIONAL_CLASS_TIERS", "FUNCTIONAL_CLASSES", "INGREDIENT_SOURCES",
    "UNCLASSIFIED_CLASS", "UNKNOWN_SOURCE", "EVIDENCE_METHODS", "EVIDENCE_SOURCE_TYPES",
    "EvidenceSpan", "PaperDocument", "SectionDocument", "TableDocument", "FigureDocument",
    "IngredientRecord", "ExperimentIngredientRecord", "IndicatorRecord", "MeasurementRecord",
    "ExperimentRecord", "ProtocolRecord", "SharedProtocol", "AssetHint", "GoldBundle",
]


# ─── Controlled values ────────────────────────────────────────────────────────
# What the models validate against and what the SQL CHECK constraints are built from.

INDICATOR_TYPES = ("microbial", "chemical")

FUNCTIONAL_CLASS_TIERS = {
    "carbohydrate": "Macronutrient", "protein": "Macronutrient", "fiber": "Macronutrient",
    "mineral": "Micronutrient",
    "phenol": "Bioactive", "essential oil": "Bioactive", "organic acid": "Bioactive",
}
FUNCTIONAL_CLASSES = tuple(FUNCTIONAL_CLASS_TIERS)
INGREDIENT_SOURCES = ("animal", "plant", "microbial", "mineral", "other")
UNCLASSIFIED_CLASS, UNKNOWN_SOURCE = "unclassified", "unknown"

# How a value was arrived at, and what kind of item supports it. Every `evidence` row
# carries both, so a derived value is never read as one the paper stated outright.
EVIDENCE_METHODS = ("stated", "derived", "inferred")
EVIDENCE_SOURCE_TYPES = ("prose", "table", "figure")


# ─── Records ──────────────────────────────────────────────────────────────────

class EvidenceSpan(BaseModel):
    """What supports one extracted field, and how far it sits from the paper's words.

    `field_name` makes a span attributable: an experiment carries several. `method` is
    the honest part — `stated`, `derived` from operands the paper supplies, or `inferred`
    on weaker grounds, the last two needing a rationale. `confidence` is not the model's
    to choose: `score_evidence` overwrites it.
    """

    model_config = ConfigDict(extra="forbid")
    field_name: str                 # "treatment" | "weight_g" | "indicator_value" | ...
    docling_item_ref: str
    page_number: int | None = None
    source_type: Literal["prose", "table", "figure"]
    source_label: str | None = None
    exact_text: str | None = None
    method: Literal["stated", "derived", "inferred"]
    rationale: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    value_is_approximate: bool = False

    @model_validator(mode="after")
    def _attribution_is_complete(self):
        if self.method != "stated":
            assert (self.rationale or "").strip(), \
                f"{self.method} evidence for {self.field_name!r} needs a rationale: a " \
                "value the paper does not state outright carries the reasoning that got there"
        elif self.source_type == "prose":
            assert (self.exact_text or "").strip(), \
                f"stated prose evidence for {self.field_name!r} needs exact_text: the " \
                "sentence the paper states it in, so the claim can be checked"
        return self

class PaperDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doi: str | None = None
    title: str
    abstract: str | None = None
    published_year: int | None = None

class SectionDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section_title: str
    content_markdown: str
    embedding: str | None = None
    docling_item_ref: str | None = None
    page_number: int | None = None

class TableDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    caption: str | None = None
    csv_filepath: str
    structured_json: dict[str, Any] = Field(default_factory=dict)
    docling_item_ref: str | None = None

class FigureDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    caption: str | None = None
    image_filepath: str
    semantic_tags: list[str] = Field(default_factory=list)
    docling_item_ref: str | None = None

class IngredientRecord(BaseModel):
    """These validate rather than coerce: a class outside the seven leaves, or a source
    that is really a table name, is a data problem best seen here."""

    model_config = ConfigDict(extra="forbid")
    ingredient_name: str
    functional_class: str
    source: str

    @field_validator("functional_class")
    @classmethod
    def _class(cls, value):
        assert value in FUNCTIONAL_CLASSES + (UNCLASSIFIED_CLASS,), \
            f"functional_class {value!r} not in {list(FUNCTIONAL_CLASSES)}"
        return value

    @field_validator("source")
    @classmethod
    def _source(cls, value):
        assert value in INGREDIENT_SOURCES + (UNKNOWN_SOURCE,), \
            f"source {value!r} not in {list(INGREDIENT_SOURCES)}; it is an origin, " \
            "not the table or arm the substance was read from"
        return value

class ExperimentIngredientRecord(BaseModel):
    """Where the dose lives. `concentration` is the only place an amount is stored."""

    model_config = ConfigDict(extra="forbid")
    ingredient_name: str
    concentration: float | None = None
    concentration_unit: str | None = None

class IndicatorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    indicator_name: str
    indicator_type: Literal["microbial", "chemical"]
    indicator_unit: str
    indicator_threshold: float | None = None

class MeasurementRecord(BaseModel):
    """One value per (day, indicator, unit) on an arm. Replicates the paper printed
    separately are averaged into it by `build_experiments`, which sets `replicates` to how
    many were folded in — 1 when the paper printed a single value or its own mean."""

    model_config = ConfigDict(extra="forbid")
    day: int
    indicator_name: str
    indicator_type: Literal["microbial", "chemical"]
    indicator_unit: str
    indicator_value: float
    indicator_threshold: float | None = None
    replicates: int = Field(default=1, ge=1)

class ExperimentRecord(BaseModel):
    """One arm, in two dimensions: `treatment` is the protocol it went through, in prose,
    and the additive dimension is `ingredients` + `experiment_ingredients`. Both nullable
    fields are None for two reasons only `evidence` tells apart — a span with the matching
    `field_name` means the paper addressed it, none means it never did."""

    model_config = ConfigDict(extra="forbid")
    meat_matrix: str
    treatment: str | None = None
    weight_g: float | None = Field(default=None, gt=0)   # one sample unit, in grams
    ingredients: list[IngredientRecord] = Field(default_factory=list)
    experiment_ingredients: list[ExperimentIngredientRecord] = Field(default_factory=list)
    indicators: list[IndicatorRecord] = Field(default_factory=list)
    measurements: list[MeasurementRecord] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)

class ProtocolRecord(BaseModel):
    """What the model adds to one arm the gate already assembled. Never measurements,
    ingredients or doses — asking for those again only invites them to be retyped.
    `experiment_index` is what joins its answer back to the arm."""

    model_config = ConfigDict(extra="forbid")
    experiment_index: int
    treatment: str | None = None
    weight_g: float | None = Field(default=None, gt=0)
    evidence: list[EvidenceSpan] = Field(default_factory=list)

class SharedProtocol(BaseModel):
    """The handling every arm of the paper went through, answered once. It is what an arm
    the model did not describe individually inherits, so a paper that states its protocol
    for all groups at once leaves no arm without one. `experimental_groups` is the count
    the methods define, which `validate_bundle_semantics` holds the gate's arms against."""

    model_config = ConfigDict(extra="ignore")
    protocol: str | None = None
    experimental_groups: int | None = Field(default=None, gt=0)
    evidence: list[EvidenceSpan] = Field(default_factory=list)

class AssetHint(BaseModel):
    """What the model may say about an asset the gate could not key: which column orders
    the rows, or that it is not a series at all. Never a value — `adjudicate_review`
    re-reads the table with this hint and the gate extracts the numbers itself."""

    model_config = ConfigDict(extra="ignore")
    docling_item_ref: str
    axis_column: str | None = None
    not_a_series: bool = False
    why: str | None = None

class GoldBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paper: PaperDocument
    sections: list[SectionDocument] = Field(default_factory=list)
    tables: list[TableDocument] = Field(default_factory=list)
    figures: list[FigureDocument] = Field(default_factory=list)
    experiments: list[ExperimentRecord] = Field(default_factory=list)
    experimental_groups: int | None = Field(default=None, gt=0)
