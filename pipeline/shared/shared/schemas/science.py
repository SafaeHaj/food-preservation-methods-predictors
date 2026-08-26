"""The extraction schema: the controlled values every record is checked against, and the
Pydantic records the pipeline assembles.

This is the single edit point for the scientific schema. Three consumers read it:

  * `shared.db.models` builds its ``CHECK`` constraints from the tuples below, so a value
    the models reject cannot reach a column either;
  * the extraction pipeline's Silver and Gold stages validate against the records;
  * `extraction.app.schemas.science` projects the records onto the HTTP API.

It lives in `shared` rather than in the extraction service because `shared.db.models` must
import the constants, and `shared` cannot depend on a service. It imports nothing beyond
stdlib and pydantic, so there is no cycle with `shared.db`.

Alembic revisions deliberately do NOT import from here. A revision is a historical record;
if it read the live tuple, editing the tuple would retroactively change what that revision
did. Changing a controlled value means writing a new revision that resyncs the constraints.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "INDICATOR_TYPES", "FUNCTIONAL_CLASS_TIERS", "FUNCTIONAL_CLASSES", "INGREDIENT_SOURCES",
    "UNCLASSIFIED_CLASS", "UNKNOWN_SOURCE", "EVIDENCE_METHODS", "EVIDENCE_SOURCE_TYPES",
    "TREATMENT_TYPES", "UNCLASSIFIED_TREATMENT", "APPLICATION_METHODS",
    "UNSPECIFIED_APPLICATION", "MATRIX_PROFILE_SOURCES", "REGULATORY_STATUSES",
    "EXTERNAL_PROVIDERS", "EXTERNAL_LOOKUP_STATUSES", "ENRICHABLE_CLASSES",
    "REVIEW_KINDS", "REVIEW_STATUSES",
    "sql_values",
    "EvidenceSpan", "PaperDocument", "SectionDocument", "TableDocument", "FigureDocument",
    "IngredientRecord", "ExperimentIngredientRecord", "IndicatorRecord", "MeasurementRecord",
    "MatrixComposition", "ExperimentRecord", "ProtocolRecord", "SharedProtocol", "AssetHint",
    "GoldBundle", "ProtocolReply", "ReviewReply",
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

# The physical intervention an arm went through, and how its additives were applied. Both
# replace free prose: `treatment` used to hold whatever the paper wrote, which no query
# could group on. The last member of each is the sink -- a real member, so the CHECK holds
# and nothing outside the set is ever invented for a value the pipeline could not classify.
TREATMENT_TYPES = (
    "High-pressure processing", "Irradiation", "UV treatment", "Ultrasound", "Cold plasma",
    "Ozone treatment", "Electrolyzed water treatment", "Water washing", "Surface trimming",
    "Heat treatment", "Vacuum treatment", "Other physical treatment",
)
UNCLASSIFIED_TREATMENT = "Other physical treatment"

APPLICATION_METHODS = (
    "Mixed", "Dipped", "Sprayed", "Washed", "Coated", "Injected", "Immersed",
    "Vacuum-packed", "Other",
)
UNSPECIFIED_APPLICATION = "Other"

# Where a `matrix_profiles` row's composition came from. `usda` rows are refreshed by the
# enrichment pass; `manual` rows are not, so a hand-corrected profile survives it.
MATRIX_PROFILE_SOURCES = ("usda", "manual")

REGULATORY_STATUSES = ("approved", "restricted", "banned", "not evaluated")

# Outbound reference providers, and what one lookup concluded. A miss is recorded as a fact
# rather than left as a gap, so the next pass can tell "not in PubChem" from "never asked".
EXTERNAL_PROVIDERS = ("pubchem", "usda")
EXTERNAL_LOOKUP_STATUSES = ("found", "not_found", "skipped", "error")

#: Functional classes whose members are single compounds, so a name resolves to one CID
#: with one molecular weight. The rest are mixtures -- "thyme essential oil" resolves to a
#: CID for the wrong thing -- and are recorded as `skipped` rather than guessed at.
ENRICHABLE_CLASSES = ("phenol", "organic acid", "mineral")

# What a queued term was being decided when the pipeline could not decide it, and where the
# curator left it. The pipeline never widens a vocabulary on its own: an unrecognised term
# falls to its sink so the data still lands, and the term itself is queued for a person to
# either add to `vocabulary.yaml` or reject. `rejected` is a real answer -- it says "this is
# not a term", which is what stops the same string being re-queued forever.
REVIEW_KINDS = ("ingredient", "indicator", "treatment", "application")
REVIEW_STATUSES = ("pending", "resolved", "rejected")


def sql_values(values) -> str:
    """A controlled vocabulary as a SQL literal list, so a CHECK constraint cannot drift
    from the tuple it came from. Inputs are the module constants above, never anything
    read from a paper.
    """
    return ", ".join("'" + str(value).replace("'", "''") + "'" for value in values)


# ─── Records ──────────────────────────────────────────────────────────────────

def strip_nul(value):
    """Drop NUL bytes from a string field.

    A PDF parse occasionally yields text carrying ``\\x00``, which PostgreSQL rejects
    outright -- and because a paper's rows are written in one transaction, a single such
    byte in one section discards the whole paper. The character carries no meaning in
    extracted prose, so removing it loses nothing and keeps the paper.
    """
    return value.replace("\x00", "") if isinstance(value, str) else value


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

    _no_nul = field_validator(
        "source_label", "exact_text", "rationale", mode="before")(strip_nul)

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

    _no_nul = field_validator("doi", "title", "abstract", mode="before")(strip_nul)


class SectionDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section_title: str
    content_markdown: str
    embedding: str | None = None
    docling_item_ref: str | None = None
    page_number: int | None = None

    _no_nul = field_validator(
        "section_title", "content_markdown", "docling_item_ref", mode="before")(strip_nul)


class TableDocument(BaseModel):
    """A gated table, projected from its `ExtractionAsset` at assembly time.

    Not persisted separately: `extraction_assets` already holds the CSV, the caption, the
    page and the bounding box, and a second row describing the same artefact is a second
    thing to keep in sync.
    """

    model_config = ConfigDict(extra="forbid")
    caption: str | None = None
    csv_filepath: str
    structured_json: dict[str, Any] = Field(default_factory=dict)
    docling_item_ref: str | None = None


class FigureDocument(BaseModel):
    """A gated figure, projected from its `ExtractionAsset`. See `TableDocument`."""

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
    source_category: str

    @field_validator("functional_class")
    @classmethod
    def _class(cls, value):
        assert value in FUNCTIONAL_CLASSES + (UNCLASSIFIED_CLASS,), \
            f"functional_class {value!r} not in {list(FUNCTIONAL_CLASSES)}"
        return value

    @field_validator("source_category")
    @classmethod
    def _source(cls, value):
        assert value in INGREDIENT_SOURCES + (UNKNOWN_SOURCE,), \
            f"source {value!r} not in {list(INGREDIENT_SOURCES)}; it is an origin, " \
            "not the table or arm the substance was read from"
        return value


class ExperimentIngredientRecord(BaseModel):
    """Where the dose lives, twice: as the paper wrote it and on one scale.

    `concentration`/`concentration_unit` are what the gate read — kept because the evidence
    rationale quotes them and because a unit the converter does not know must still be
    visible rather than silently absent. `concentration_ppm` is what everything downstream
    sums, and is None when no conversion exists, never zero.
    """

    model_config = ConfigDict(extra="forbid")
    ingredient_name: str
    concentration: float | None = None
    concentration_unit: str | None = None
    concentration_ppm: float | None = Field(default=None, ge=0)
    application_method: str = UNSPECIFIED_APPLICATION

    @field_validator("application_method")
    @classmethod
    def _application(cls, value):
        assert value in APPLICATION_METHODS, \
            f"application_method {value!r} not in {list(APPLICATION_METHODS)}"
        return value


class IndicatorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    indicator_name: str
    indicator_type: Literal["microbial", "chemical"]
    indicator_unit: str
    indicator_threshold: float | None = None


class MeasurementRecord(BaseModel):
    """One value per (day, indicator, unit) on an arm.

    Papers publish a mean, and that mean is what gets extracted, so there is no count of
    folded readings to keep: separately-printed series for the same arm are averaged by
    `build_experiments` and the result is a value like any other.
    """

    model_config = ConfigDict(extra="forbid")
    day: int = Field(ge=0)
    indicator_name: str
    indicator_type: Literal["microbial", "chemical"]
    indicator_unit: str
    indicator_value: float
    indicator_threshold: float | None = None


class MatrixComposition(BaseModel):
    """The physicochemical description of a food matrix.

    Carried in two places on purpose. On `matrix_profiles` it is the reference value for a
    named food, filled from USDA; on an experiment it is what *that paper measured*. A
    reader COALESCEs the two and can still tell which it got, because a measured value is
    the one that is not null on the experiment — which is the 05 Aug minutes' rule that
    external or inferred values must not be treated as equivalent to measured ones, made
    structural instead of documentary.
    """

    model_config = ConfigDict(extra="forbid")
    ph: float | None = Field(default=None, gt=0, le=14)
    water_activity: float | None = Field(default=None, gt=0, le=1)
    moisture_percent: float | None = Field(default=None, ge=0, le=100)
    fat_percent: float | None = Field(default=None, ge=0, le=100)
    protein_percent: float | None = Field(default=None, ge=0, le=100)
    salt_percent: float | None = Field(default=None, ge=0, le=100)
    initial_tvc_log_cfu_g: float | None = Field(default=None, ge=0)


class ExperimentRecord(BaseModel):
    """One arm, in three dimensions: the matrix it was applied to, the physical treatment
    it went through, and the additives it carried.

    `matrix_name` resolves to a `matrix_profiles` row by the writer; `composition` holds
    only what this paper measured, and is empty when it measured nothing. `treatment_type`
    is a closed value and `treatment_description` keeps the sentence it came from, so a
    classification that goes wrong is legible rather than lost.

    `arm_key` is what makes one arm distinct from another *within a paper*, and it is none
    of the three dimensions above: two rungs of a dose ladder share a matrix, a treatment
    and a substance, differing only in how much. Silver builds it from the arm's substances
    and their amounts, which is the only thing that separates them, so the writer keys on
    it rather than re-deriving an identity the pipeline already established.
    """

    model_config = ConfigDict(extra="forbid")
    matrix_name: str
    arm_key: str = ""
    composition: MatrixComposition = Field(default_factory=MatrixComposition)
    treatment_type: str | None = None
    treatment_description: str | None = None
    thermal_temperature_c: float | None = None
    thermal_duration_min: float | None = Field(default=None, ge=0)
    sample_weight_g: float | None = Field(default=None, gt=0)   # one sample unit, in grams
    storage_temperature_c: float | None = None
    map_o2_percent: float | None = Field(default=None, ge=0, le=100)
    map_co2_percent: float | None = Field(default=None, ge=0, le=100)
    map_n2_percent: float | None = Field(default=None, ge=0, le=100)
    packaging_description: str | None = None
    ingredients: list[IngredientRecord] = Field(default_factory=list)
    experiment_ingredients: list[ExperimentIngredientRecord] = Field(default_factory=list)
    indicators: list[IndicatorRecord] = Field(default_factory=list)
    measurements: list[MeasurementRecord] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)

    @field_validator("treatment_type")
    @classmethod
    def _treatment(cls, value):
        assert value is None or value in TREATMENT_TYPES, \
            f"treatment_type {value!r} not in {list(TREATMENT_TYPES)}"
        return value


class ProtocolRecord(BaseModel):
    """What the model adds to one arm the gate already assembled. Never measurements,
    ingredients or doses — asking for those again only invites them to be retyped.
    `experiment_index` is what joins its answer back to the arm.

    `treatment_type` and `application_method` are closed sets appended to a call that was
    already being made, which is what makes them free: the deterministic classifier in
    `silver.classify` answers most arms from keywords, and only the ones it could not key —
    no match, or two — arrive here. The values are re-checked against the tuples in Python
    after the reply, so a model cannot widen either set.

    Both carry their vocabulary as a schema `enum` rather than relying on the prompt to
    describe it. Measured against Gemini: with the values only in the prose, constrained
    decoding returned `null` for both on a sentence that plainly said "blanched at 85 C"
    and "dipped" — while the *unconstrained* call got both right. A schema saying only
    "string or null" gives the decoder no reason to prefer a vocabulary word, and null is
    the cheapest token that satisfies it. The enum makes the closed set binding on
    generation, which is the whole point of sending a schema at all.

    The enum lists the vocabulary only. `null` is not a member: it is permitted by the
    field's `nullable`, and the `google-genai` SDK validates every enum entry as a string
    and rejects a `None` among them before the request is ever sent.
    """

    model_config = ConfigDict(extra="forbid")
    experiment_index: int
    treatment_type: str | None = Field(
        default=None, json_schema_extra={"enum": list(TREATMENT_TYPES)})
    treatment_description: str | None = None
    application_method: str | None = Field(
        default=None, json_schema_extra={"enum": list(APPLICATION_METHODS)})
    thermal_temperature_c: float | None = None
    thermal_duration_min: float | None = Field(default=None, ge=0)
    sample_weight_g: float | None = Field(default=None, gt=0)
    storage_temperature_c: float | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)

    @field_validator("treatment_type")
    @classmethod
    def _treatment(cls, value):
        return value if value in TREATMENT_TYPES else None

    @field_validator("application_method")
    @classmethod
    def _application(cls, value):
        return value if value in APPLICATION_METHODS else None


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


# ─── Model replies ────────────────────────────────────────────────────────────
# What each of the two LLM calls actually returns. They are separate from `GoldBundle`
# on purpose: handing a provider `GoldBundle.model_json_schema()` as the decoding grammar
# for a call that returns protocol records constrains generation to the wrong shape.

class ProtocolReply(BaseModel):
    """The Gold call's answer: the shared protocol plus per-arm prose fields."""

    model_config = ConfigDict(extra="ignore")
    protocol: str | None = None
    experimental_groups: int | None = Field(default=None, gt=0)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    experiments: list[ProtocolRecord] = Field(default_factory=list)


class ReviewReply(BaseModel):
    """The review call's answer: how to key the assets the gate could not."""

    model_config = ConfigDict(extra="ignore")
    assets: list[AssetHint] = Field(default_factory=list)
