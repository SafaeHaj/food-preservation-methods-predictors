"""
SQLAlchemy ORM models for the Food Research Platform.

Canonical scientific schema (five tables + evidence):

    Project → Paper → Experiment  --< ExperimentIngredient >--  Ingredient
                                  \\--< Measurement (day, value) >--  Indicator

  Evidence anchors any of those rows to an exact location in the source PDF.

These tables carried an `ext_` prefix while a second, parallel hierarchy
(Study → Experiment → TreatmentArm → Observation) still existed and owned the unprefixed
names. That hierarchy is gone -- nothing produced data for it except a promoter that
transcribed these very tables into it -- so the prefix has gone with it. This IS the
canonical schema; there is no other.

Supporting:
  Section                     the paper's prose, as Silver segmented it
  Job, ExtractionRun          async work and its audit trail
  AuditEvent                  immutable action log
  VocabularyReviewQueue       terms the pipeline could not name, awaiting a curator
  ProjectMember               team roles
  DoclingCache, FigureConversionCache     parse/chart-conversion caches, keyed by file hash
  ExtractionAsset, AssetContextLink       the extraction workspace (figures, tables, charts)

Platform:
  User, Project, Paper

──────────────────────────────────────────────────────────────────────────────
Controlled vocabularies
──────────────────────────────────────────────────────────────────────────────
The `CHECK` constraints on ingredients, indicators and evidence are built from the tuples
in `shared.schemas.science`, not written out here. The Pydantic records the pipeline
validates against and the columns those records land in therefore cannot disagree: a value
the models reject has no way into a column either.

Alembic revisions inline the literals instead of importing them -- see the module docstring
of `shared.schemas.science` for why -- so changing a vocabulary means writing a revision
that resyncs the constraints. `pipeline/shared/tests/test_check_constraints.py` fails when
that is forgotten, because `alembic --autogenerate` does not detect CHECK drift.

──────────────────────────────────────────────────────────────────────────────
Foreign-key deletion policy
──────────────────────────────────────────────────────────────────────────────
Every FK declares an explicit `ondelete`. Two exceptions are marked RESTRICT in place
with a comment saying why. Pick the rule, don't reason case by case -- deciding ad hoc
is how `jobs.paper_id` ended up with no policy and made deleting a paper impossible.

  1. Tenancy root  -- anything scoped to `projects.id`            → CASCADE
  2. Ownership     -- child cannot exist without its parent       → CASCADE
                      (nullable=False structural edges)
  3. Provenance    -- nullable pointer at the work that produced  → SET NULL
                      the row; the row outlives it (jobs, runs)
  4. Attribution   -- nullable `users.id` (created_by, actor_id)  → SET NULL
  5. Cross-ref     -- nullable optional pointer at a sibling      → SET NULL

Note the asymmetry on `jobs`: `paper_id` is SET NULL (the paper goes, the project
stays, the run history stays queryable) while `project_id` is CASCADE (the whole tenant
is gone, so is its history).

A relationship whose child FK is CASCADE must also set `passive_deletes=True`, or
SQLAlchemy loads every child and issues its own UPDATE/DELETE, silently bypassing the
database rule this policy exists to establish.
"""

import json
from datetime import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from shared.db.database import Base
from shared.schemas.science import (
    APPLICATION_METHODS, EVIDENCE_METHODS, EVIDENCE_SOURCE_TYPES, EXTERNAL_LOOKUP_STATUSES,
    EXTERNAL_PROVIDERS, FUNCTIONAL_CLASSES, INDICATOR_TYPES, INGREDIENT_SOURCES,
    MATRIX_PROFILE_SOURCES, REGULATORY_STATUSES, REVIEW_KINDS, REVIEW_STATUSES,
    TREATMENT_TYPES, UNCLASSIFIED_CLASS, UNKNOWN_SOURCE, UNSPECIFIED_APPLICATION, sql_values,
)


# ════════════════════════════════════════════════════════════════════════════
# PLATFORM
# ════════════════════════════════════════════════════════════════════════════

class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    email         = Column(String, unique=True, index=True, nullable=False)
    full_name     = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

    projects        = relationship("Project", back_populates="owner")
    project_members = relationship("ProjectMember", back_populates="user", foreign_keys="ProjectMember.user_id")
    audit_events    = relationship("AuditEvent", back_populates="actor", foreign_keys="AuditEvent.actor_id")


class Project(Base):
    __tablename__ = "projects"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String, nullable=False)
    description   = Column(Text, default="")
    schema_json   = Column(Text, default="[]")
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Deliberately RESTRICT (no ondelete): a project must always have an owner, so deleting
    # a user with projects should fail loudly rather than orphan or cascade them.
    owner_id      = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner         = relationship("User", back_populates="projects")
    papers        = relationship("Paper", back_populates="project", cascade="all, delete-orphan", passive_deletes=True)
    members       = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan", passive_deletes=True)

    # The scientific tables carry `project_id ON DELETE CASCADE` but no ORM relationship:
    # a project delete is a database cascade, not a Python loop over several thousand
    # measurement rows.

    @property
    def schema(self):
        return json.loads(self.schema_json) if self.schema_json else []


class Paper(Base):
    __tablename__ = "papers"

    id            = Column(Integer, primary_key=True, index=True)
    project_id    = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    filename      = Column(String, nullable=False)
    original_name = Column(String, nullable=False)
    file_path     = Column(String, nullable=False)
    file_hash     = Column(String(64), index=True)   # SHA-256
    page_count    = Column(Integer, default=0)
    status        = Column(String, default="uploaded")
    error_message = Column(Text, default="")
    uploaded_at   = Column(DateTime, default=datetime.utcnow)

    # Bibliography, read out of the parsed document. Nullable throughout: a paper exists
    # from the moment it is uploaded, and that is before anything has read its title.
    doi            = Column(String, index=True, nullable=True)
    title          = Column(String, nullable=True)
    abstract       = Column(Text, nullable=True)
    published_year = Column(Integer, nullable=True)

    project         = relationship("Project", back_populates="papers")
    sections        = relationship("Section", back_populates="paper", cascade="all, delete-orphan", passive_deletes=True)
    extraction_runs = relationship("ExtractionRun", back_populates="paper", cascade="all, delete-orphan", passive_deletes=True)
    # No cascade: jobs are the async audit trail and outlive the paper they ran on
    # (`jobs.paper_id` is ON DELETE SET NULL). This relationship exists so the ORM is aware
    # of the table at all -- its absence is what made deleting a paper fail on the FK.
    jobs            = relationship("Job", back_populates="paper", passive_deletes=True)


class Section(Base):
    """One heading-delimited stretch of a paper's prose.

    `extraction_assets` holds the figures and the tables; nothing held the text between
    them. Silver needs it to resolve a figure's local context, Gold's prompt is built from
    it, and a `prose` evidence span's `docling_item_ref` resolves into it -- so a span
    citing a sentence had no row to point at.
    """
    __tablename__ = "sections"

    id               = Column(Integer, primary_key=True, index=True)
    paper_id         = Column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    section_order    = Column(Integer, nullable=True)
    section_title    = Column(String, nullable=False)
    content_markdown = Column(Text, nullable=False)
    page_number      = Column(Integer, nullable=True)
    docling_item_ref = Column(String, nullable=True)
    #: Reserved for a future semantic index; the pipeline writes null today.
    embedding        = Column(Text, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)

    paper = relationship("Paper", back_populates="sections")


# ════════════════════════════════════════════════════════════════════════════
# INFRASTRUCTURE: Jobs and extraction runs
# ════════════════════════════════════════════════════════════════════════════

class Job(Base):
    """Tracks all async work. Survives backend restarts via DB."""
    __tablename__ = "jobs"

    id              = Column(Integer, primary_key=True, index=True)
    project_id      = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    paper_id        = Column(Integer, ForeignKey("papers.id", ondelete="SET NULL"), nullable=True)
    job_type        = Column(String, nullable=False)
    # workspace_extraction | paper_ingestion | ingredient_enrichment | dataset_build
    status          = Column(String, default="queued") # queued|running|completed|partial_success|failed|cancelled
    progress        = Column(Integer, default=0)        # 0-100
    current_step    = Column(String, default="")
    total_steps     = Column(Integer, default=0)
    error_message   = Column(Text, default="")
    result_json     = Column(Text, default="{}")
    idempotency_key = Column(String, unique=True, index=True, nullable=True)
    celery_task_id  = Column(String, index=True, nullable=True)
    created_by      = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    started_at      = Column(DateTime, nullable=True)
    completed_at    = Column(DateTime, nullable=True)

    extraction_run  = relationship("ExtractionRun", back_populates="job", uselist=False)
    paper           = relationship("Paper", back_populates="jobs")

    @property
    def result(self):
        # Tolerant on read: a job written by an older revision may hold anything.
        try:
            return json.loads(self.result_json) if self.result_json else {}
        except (TypeError, ValueError):
            return {}

    @result.setter
    def result(self, value):
        """Serialize on assignment so no caller has to remember `json.dumps`.

        Every task previously wrote `result_json` by hand, and each picked its own key
        names and its own idea of what an empty result looked like ("{}" vs "" vs null).
        """
        self.result_json = json.dumps(value or {}, default=str)


class ExtractionRun(Base):
    """One extraction attempt for one paper."""
    __tablename__ = "extraction_runs"

    id              = Column(Integer, primary_key=True, index=True)
    paper_id        = Column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    job_id          = Column(Integer, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    provider        = Column(String)        # vertexai|google_ai|openai|anthropic|ollama|groq
    model_name      = Column(String)
    prompt_version  = Column(String)
    status          = Column(String, default="pending")
    pages_processed = Column(Integer, default=0)
    chunks_created  = Column(Integer, default=0)
    rows_extracted  = Column(Integer, default=0)
    tables_found    = Column(Integer, default=0)
    error_message   = Column(Text, default="")
    created_at      = Column(DateTime, default=datetime.utcnow)
    completed_at    = Column(DateTime, nullable=True)

    paper  = relationship("Paper", back_populates="extraction_runs")
    job    = relationship("Job", back_populates="extraction_run")


# ════════════════════════════════════════════════════════════════════════════
# AUDIT
# ════════════════════════════════════════════════════════════════════════════

class AuditEvent(Base):
    """Immutable record of every create/update/delete/approve/reject action."""
    __tablename__ = "audit_events"

    id            = Column(Integer, primary_key=True, index=True)
    actor_id      = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    entity_type   = Column(String, nullable=False, index=True)
    entity_id     = Column(Integer, nullable=False, index=True)
    action        = Column(String, nullable=False)  # create|update|delete|import|export
    before_json   = Column(Text)
    after_json    = Column(Text)
    diff_json     = Column(Text)    # only changed fields
    reason        = Column(Text)
    source        = Column(String)  # user|ai_extraction|import
    ip_address    = Column(String)
    project_id    = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow, index=True)

    actor = relationship("User", back_populates="audit_events", foreign_keys=[actor_id])

    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )


# ════════════════════════════════════════════════════════════════════════════
# COLLABORATION
# ════════════════════════════════════════════════════════════════════════════

class ProjectMember(Base):
    """Team roles within a project."""
    __tablename__ = "project_members"

    id          = Column(Integer, primary_key=True, index=True)
    project_id  = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    # Deliberately RESTRICT (no ondelete): a membership row without a user is meaningless,
    # and silently dropping someone's access on user deletion would be worse than failing.
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    role        = Column(String, nullable=False)   # owner|admin|reviewer|analyst|viewer
    invited_by  = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    joined_at   = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="members")
    user    = relationship("User", back_populates="project_members", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_member"),
    )


# ════════════════════════════════════════════════════════════════════════════
# CANONICAL SCIENTIFIC SCHEMA
# ════════════════════════════════════════════════════════════════════════════
# The five tables the extraction pipeline writes, plus row-level evidence. Everything
# downstream -- the scientific database screens, the dataset builder, prediction -- reads
# these and nothing else.

class MatrixProfile(Base):
    """A named food matrix and its reference composition — global, not per project.

    "Chicken breast" is the same food in every project, and its USDA composition is the
    same number however many times it is looked up. Scoping it per project would mean one
    outbound request per project per matrix and N copies of one fact, which then drift.

    Every field here is the *reference* value. The measured counterparts live on
    `experiments` under the same names, and a reader COALESCEs the two -- so a query can
    always tell a value a paper reported from one a database supplied.
    """
    __tablename__ = "matrix_profiles"

    id                    = Column(Integer, primary_key=True, index=True)
    matrix_name           = Column(String, nullable=False, unique=True, index=True)
    ph                    = Column(Float, nullable=True)
    water_activity        = Column(Float, nullable=True)
    moisture_percent      = Column(Float, nullable=True)
    fat_percent           = Column(Float, nullable=True)
    protein_percent       = Column(Float, nullable=True)
    salt_percent          = Column(Float, nullable=True)
    initial_tvc_log_cfu_g = Column(Float, nullable=True)
    reference_weight_g    = Column(Float, nullable=True)
    source                = Column(String, nullable=True)   # see MATRIX_PROFILE_SOURCES
    external_id           = Column(String, nullable=True)   # FDC id
    fetched_at            = Column(DateTime, nullable=True)
    created_at            = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("ph IS NULL OR (ph > 0 AND ph <= 14)", name="ck_matrix_ph_range"),
        CheckConstraint("water_activity IS NULL OR (water_activity > 0 AND water_activity <= 1)",
                        name="ck_matrix_water_activity_range"),
        CheckConstraint(f"source IS NULL OR source IN ({sql_values(MATRIX_PROFILE_SOURCES)})",
                        name="ck_matrix_profiles_source"),
    )


class TreatmentProfile(Base):
    """One distinct physical treatment, deduplicated across the corpus.

    `treatment_key` exists because a three-column UNIQUE cannot dedupe: two rows whose
    temperature and duration are both NULL compare as distinct in SQL, so every unqualified
    "Irradiation" would insert a new row. The writer builds the key as "type|temp|dur" with
    a literal for the nulls, which collapses them.
    """
    __tablename__ = "treatment_profiles"

    id                    = Column(Integer, primary_key=True, index=True)
    treatment_type        = Column(String, nullable=False)   # see TREATMENT_TYPES
    thermal_temperature_c = Column(Float, nullable=True)
    thermal_duration_min  = Column(Float, nullable=True)
    treatment_key         = Column(String, nullable=False, unique=True, index=True)
    created_at            = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(f"treatment_type IN ({sql_values(TREATMENT_TYPES)})",
                        name="ck_treatment_profiles_type"),
        CheckConstraint("thermal_duration_min IS NULL OR thermal_duration_min >= 0",
                        name="ck_treatment_duration_non_negative"),
    )


class Ingredient(Base):
    """Reusable ingredient catalogue — one row per unique ingredient name, corpus-wide.

    Global rather than per project (as `matrix_profiles` is, and for the same reason): the
    molecular features and regulatory status hanging off an ingredient describe the
    substance, not one team's use of it, and duplicating "nisin" per project would mean
    re-fetching PubChem for each copy.
    """
    __tablename__ = "ingredients"

    id                  = Column(Integer, primary_key=True, index=True)
    ingredient_name     = Column(String, nullable=False, unique=True, index=True)
    functional_class    = Column(String, nullable=False)   # see FUNCTIONAL_CLASSES
    source_category     = Column(String, nullable=False)   # biological origin, NOT paper
    created_at          = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            f"functional_class IN ({sql_values(FUNCTIONAL_CLASSES + (UNCLASSIFIED_CLASS,))})",
            name="ck_ingredients_functional_class",
        ),
        CheckConstraint(
            f"source_category IN ({sql_values(INGREDIENT_SOURCES + (UNKNOWN_SOURCE,))})",
            name="ck_ingredients_source",
        ),
    )


class VocabularyReviewQueue(Base):
    """A term the pipeline could not name, waiting on a person to name it.

    The pipeline never widens its own vocabulary. When a substance is not in
    `vocabulary.yaml`, or a protocol sentence matches two treatment families at once, the
    value falls to its sink so the data still lands -- and the term lands here, where a
    curator either adds it to the vocabulary or rejects it. That is the whole difference
    between "recorded as unclassified and reviewed" and "silently given a new category".

    Global rather than per project, as `ingredients` and `matrix_profiles` are: what a term
    means is a fact about the term. `UNIQUE(kind, canonical_key)` is what makes one unknown
    substance appearing in forty papers a single row with `occurrences = 40` rather than
    forty rows nobody can triage.

    `raw_text` keeps the paper's own wording, not the canonical key: a curator adding the
    term to the vocabulary needs to see what was actually written, and `canonical_key`
    folds away the case and punctuation that distinguish "Nisin A" from "nisin-a".
    """
    __tablename__ = "vocabulary_review_queue"

    id                  = Column(Integer, primary_key=True, index=True)
    kind                = Column(String, nullable=False, index=True)   # see REVIEW_KINDS
    raw_text            = Column(String, nullable=False)   # as the paper wrote it
    canonical_key       = Column(String, nullable=False)   # the dedup key
    status              = Column(String, nullable=False, default="pending",
                                 server_default="pending", index=True)
    #: Bumped every time the term is met again. The queue is worked highest-first, so this
    #: is what puts the term blocking forty papers above the one blocking a single arm.
    occurrences         = Column(Integer, nullable=False, default=1, server_default="1")
    first_seen_paper_id = Column(Integer, ForeignKey("papers.id", ondelete="SET NULL"),
                                 nullable=True)
    last_seen_at        = Column(DateTime, default=datetime.utcnow)
    resolved_at         = Column(DateTime, nullable=True)
    resolved_by         = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                                 nullable=True)
    note                = Column(Text, nullable=True)      # why it was resolved or rejected
    created_at          = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("kind", "canonical_key", name="uq_review_queue_kind_key"),
        CheckConstraint(f"kind IN ({sql_values(REVIEW_KINDS)})", name="ck_review_queue_kind"),
        CheckConstraint(f"status IN ({sql_values(REVIEW_STATUSES)})",
                        name="ck_review_queue_status"),
        CheckConstraint("occurrences >= 0", name="ck_review_queue_occurrences_non_negative"),
    )


class Experiment(Base):
    """One arm of a paper, in three dimensions: matrix, treatment, additives.

    `matrix_id` and `treatment_id` replace the `meat_matrix` and `treatment` prose columns.
    Both are RESTRICT rather than CASCADE -- the third documented exception to the FK policy
    above. A reference row several experiments point at must not vanish under them, and
    unlike a project or a paper there is no owning tenant whose deletion should take it.

    The composition block is what *this paper measured*. A null falls back to the matrix
    profile's reference value, and the difference between the two is exactly the provenance
    distinction the 05 Aug minutes require -- so it is a column, not a convention.
    """
    __tablename__ = "experiments"

    id                    = Column(Integer, primary_key=True, index=True)
    project_id            = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    paper_id              = Column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id                = Column(Integer, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    matrix_id             = Column(Integer, ForeignKey("matrix_profiles.id", ondelete="RESTRICT"), nullable=False, index=True)
    treatment_id          = Column(Integer, ForeignKey("treatment_profiles.id", ondelete="RESTRICT"), nullable=True, index=True)
    treatment_description = Column(Text, nullable=True)    # the sentence it was classified from
    #: What separates this arm from the others in the same paper. Matrix and treatment do
    #: not: a dose ladder shares both and differs only in amount, so keying an arm on them
    #: collapses the whole ladder into one row. Silver builds this from the arm's
    #: substances and their doses; it is meaningful only within a paper.
    arm_key               = Column(String, nullable=False, server_default="", default="")
    sample_weight_g       = Column(Float, nullable=True)   # one sample unit, in grams
    storage_temperature_c = Column(Float, nullable=True)
    map_o2_percent        = Column(Float, nullable=True)
    map_co2_percent       = Column(Float, nullable=True)
    map_n2_percent        = Column(Float, nullable=True)
    packaging_description = Column(Text, nullable=True)

    # MEASURED composition -- same names as `matrix_profiles`, different meaning (see above)
    ph                    = Column(Float, nullable=True)
    water_activity        = Column(Float, nullable=True)
    moisture_percent      = Column(Float, nullable=True)
    fat_percent           = Column(Float, nullable=True)
    protein_percent       = Column(Float, nullable=True)
    salt_percent          = Column(Float, nullable=True)
    initial_tvc_log_cfu_g = Column(Float, nullable=True)

    created_at            = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("sample_weight_g IS NULL OR sample_weight_g > 0",
                        name="ck_experiments_weight_positive"),
        CheckConstraint("ph IS NULL OR (ph > 0 AND ph <= 14)", name="ck_experiments_ph_range"),
        CheckConstraint("water_activity IS NULL OR (water_activity > 0 AND water_activity <= 1)",
                        name="ck_experiments_water_activity_range"),
        # Backs the writer's get-or-create: re-extracting a paper must find the arm it
        # wrote last time rather than duplicate it.
        Index("ix_experiments_identity", "project_id", "paper_id", "matrix_id",
              "treatment_id", "arm_key"),
    )


class ExperimentIngredient(Base):
    """Junction: many experiments ↔ many ingredients, with dose and how it was applied.

    `concentration_ppm` is nullable and that null is meaningful: a paper naming an additive
    without a dose is common, and so is one whose unit carries no mass basis (`IU/g`, a
    peak-area percentage) and therefore cannot be converted. Neither is a zero. Which of
    the two it was is recorded in the ingestion job's `unit_report`, not guessed at here.
    """
    __tablename__ = "experiment_ingredients"

    experiment_id       = Column(Integer, ForeignKey("experiments.id", ondelete="CASCADE"), primary_key=True)
    ingredient_id       = Column(Integer, ForeignKey("ingredients.id", ondelete="CASCADE"), primary_key=True)
    concentration_ppm   = Column(Float, nullable=True)
    application_method  = Column(String, nullable=False,
                                 default=UNSPECIFIED_APPLICATION,
                                 server_default=UNSPECIFIED_APPLICATION)

    __table_args__ = (
        CheckConstraint("concentration_ppm IS NULL OR concentration_ppm >= 0",
                        name="ck_experiment_ingredients_ppm_non_negative"),
        CheckConstraint(f"application_method IN ({sql_values(APPLICATION_METHODS)})",
                        name="ck_experiment_ingredients_application"),
    )


class Indicator(Base):
    """Reusable indicator catalogue — one row per unique (name, unit), corpus-wide.

    `indicator_name` is what the paper calls it ("Total viable count"); `indicator_type` is
    the two-valued category it belongs to. They were one column, which meant the display
    name and the category could not both be stored -- and keying on the category alone
    would fold every microbial count in log CFU/g into a single row.

    `indicator_threshold` is the scientific or regulatory limit: the value a measurement
    crosses to end shelf life. It is what a survival label is derived from, which is why it
    lives here rather than in a separate definitions table -- a threshold with no indicator
    to apply it to means nothing. There is no comparison operator beside it, because
    spoilage is always `indicator_value >= threshold`; an operator column would only be a
    way to write that wrong.
    """
    __tablename__ = "indicators"

    id                  = Column(Integer, primary_key=True, index=True)
    indicator_name      = Column(String, nullable=False)   # e.g. "Total viable count"
    indicator_type      = Column(String, nullable=False)   # see INDICATOR_TYPES
    indicator_unit      = Column(String, nullable=False)   # e.g. "log CFU/g"
    indicator_threshold = Column(Float, nullable=True)     # e.g. 7 (regulatory limit)
    created_at          = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("indicator_name", "indicator_unit", name="uq_indicator_name_unit"),
        CheckConstraint(f"indicator_type IN ({sql_values(INDICATOR_TYPES)})",
                        name="ck_indicators_type"),
    )


class Measurement(Base):
    """One value per (experiment, day, indicator) — composite primary key.

    There is no replicate count. Papers publish a mean and that mean is what gets
    extracted; where a paper printed several series for one arm, `build_experiments`
    averages them and the result is a value like any other.
    """
    __tablename__ = "measurements"

    experiment_id       = Column(Integer, ForeignKey("experiments.id", ondelete="CASCADE"), primary_key=True)
    day                 = Column(Integer, primary_key=True)
    indicator_id        = Column(Integer, ForeignKey("indicators.id", ondelete="CASCADE"), primary_key=True)
    indicator_value     = Column(Float, nullable=False)

    __table_args__ = (
        CheckConstraint("day >= 0", name="ck_measurements_day_non_negative"),
    )


class Evidence(Base):
    """Row-level evidence linking extracted values to exact PDF locations.

    `method` and `rationale` say how far the value sits from the paper's own words: a
    `derived` or `inferred` value carries the reasoning that produced it, so it is never
    read as one the paper stated outright. `confidence` is computed by the pipeline's
    scorer against the source text; it is not a number the model supplies.
    """
    __tablename__ = "evidence"

    id                  = Column(Integer, primary_key=True, index=True)
    paper_id            = Column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type         = Column(String, nullable=False)   # experiment|ingredient_link|measurement
    # Composite entity key stored as JSON string, e.g. '{"experiment_id":5,"day":3,"indicator_id":2}'
    entity_key          = Column(Text, nullable=False)
    # NOT NULL: an experiment carries several spans, and one that does not say which field
    # it supports cannot be attributed to any of them.
    field_name          = Column(String, nullable=False)
    page_number         = Column(Integer, nullable=True)
    source_type         = Column(String, nullable=False)   # see EVIDENCE_SOURCE_TYPES
    source_label        = Column(String, nullable=True)    # "Table 2", "Figure 3", ...
    exact_text          = Column(Text, nullable=True)
    method              = Column(String, nullable=False)   # see EVIDENCE_METHODS
    rationale           = Column(Text, nullable=True)      # required unless method='stated'
    bbox_x1             = Column(Float, nullable=True)
    bbox_y1             = Column(Float, nullable=True)
    bbox_x2             = Column(Float, nullable=True)
    bbox_y2             = Column(Float, nullable=True)
    confidence          = Column(Float, nullable=True)
    # Chart-specific fields
    figure_series       = Column(String, nullable=True)
    x_axis_value        = Column(Float, nullable=True)
    y_axis_value        = Column(Float, nullable=True)
    value_is_approximate = Column(Boolean, default=False)
    # Backend-generated image paths (never returned by LLM)
    evidence_image_path    = Column(String, nullable=True)
    evidence_thumbnail_path = Column(String, nullable=True)
    # Docling provenance anchor — set by the extraction pipeline
    docling_item_ref    = Column(String, nullable=True)    # e.g. "#/tables/0", "#/texts/5"
    is_chart_derived    = Column(Boolean, default=False)   # True when value came from chart CSV

    __table_args__ = (
        CheckConstraint(f"method IN ({sql_values(EVIDENCE_METHODS)})", name="ck_evidence_method"),
        CheckConstraint(f"source_type IN ({sql_values(EVIDENCE_SOURCE_TYPES)})",
                        name="ck_evidence_source_type"),
        CheckConstraint("method = 'stated' OR (rationale IS NOT NULL AND rationale != '')",
                        name="ck_evidence_rationale_when_not_stated"),
    )


# ─── Docling extraction cache ──────────────────────────────────────────────────

class DoclingCache(Base):
    """One row per PDF (identified by file SHA-256 hash). Stores paths to extracted artefacts."""
    __tablename__ = "docling_cache"

    id              = Column(Integer, primary_key=True, index=True)
    paper_id        = Column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    file_hash       = Column(String(64), unique=True, nullable=False, index=True)
    cache_dir       = Column(String, nullable=False)       # absolute path to cache folder
    markdown_path   = Column(String, nullable=True)
    table_count     = Column(Integer, default=0)
    figure_count    = Column(Integer, default=0)
    page_count      = Column(Integer, default=0)
    docling_version = Column(String, nullable=False)       # bump to invalidate cache
    #: Where the Silver stage left this paper's gated package. The workspace job writes it,
    #: the ingestion job reads it; a null or stale pointer means Silver is recomputed from
    #: the cached parse rather than the paper failing.
    silver_package_path = Column(String, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)

    figure_conversions = relationship(
        "FigureConversionCache", back_populates="docling_cache",
        cascade="all, delete-orphan", passive_deletes=True,
    )


class FigureConversionCache(Base):
    """PP-Chart2Table result for one extracted figure image."""
    __tablename__ = "figure_conversion_cache"

    id               = Column(Integer, primary_key=True, index=True)
    docling_cache_id = Column(Integer, ForeignKey("docling_cache.id", ondelete="CASCADE"), nullable=False, index=True)
    figure_index     = Column(Integer, nullable=False)     # image_N counter
    item_ref         = Column(String, nullable=True)       # Docling self_ref
    image_path       = Column(String, nullable=False)
    image_hash       = Column(String(64), nullable=True)
    csv_path         = Column(String, nullable=True)       # null when rejected
    status           = Column(String, nullable=False)      # valid | rejected | error
    reject_reason    = Column(String, nullable=True)
    row_count        = Column(Integer, default=0)
    col_count        = Column(Integer, default=0)
    created_at       = Column(DateTime, default=datetime.utcnow)

    docling_cache    = relationship("DoclingCache", back_populates="figure_conversions")


# ─── Extraction Workspace ──────────────────────────────────────────────────────

class ExtractionAsset(Base):
    """
    One row per visual or tabular element extracted from a PDF.
    Central record for the Extraction Workspace (figures, charts, native tables).
    """
    __tablename__ = "extraction_assets"

    id                  = Column(Integer, primary_key=True, index=True)
    paper_id            = Column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id          = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id              = Column(Integer, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    docling_item_ref    = Column(String, nullable=True)
    asset_type          = Column(String, nullable=False)        # figure | native_table
    page_number         = Column(Integer, nullable=True)
    bbox_json           = Column(Text, nullable=True)           # {"x1","y1","x2","y2"} fractional
    section_name        = Column(String, nullable=True)
    caption             = Column(Text, nullable=True)
    image_path          = Column(String, nullable=True)         # figure PNG
    csv_path            = Column(String, nullable=True)         # chart CSV from PP-Chart2Table
    page_image_path     = Column(String, nullable=True)         # full page PNG
    classification      = Column(String, default="unknown")
    # chart | native_table | photograph | diagram | chemical_structure | multi_panel_figure | unknown
    conversion_status   = Column(String, nullable=True)
    # pending | processing | complete | failed | skipped | not_a_chart | not_applicable
    conversion_error    = Column(String, nullable=True)
    csv_rows            = Column(Integer, nullable=True)
    csv_cols            = Column(Integer, nullable=True)
    relevance_score     = Column(Float, default=0.0)
    selected_for_llm    = Column(Boolean, default=False)
    user_note           = Column(Text, nullable=True)
    # The schema gate's structural verdict, distinct from `relevance_score`: the score is a
    # keyword heuristic driving the curation screen, the gate decides whether the asset
    # actually carries an ordered series the pipeline can read.
    gate_verdict        = Column(String, nullable=True)
    # accepted | reference | review | rejected
    gate_json           = Column(Text, nullable=True)      # axis, points, why
    created_at          = Column(DateTime, default=datetime.utcnow)

    context_links = relationship(
        "AssetContextLink", back_populates="asset",
        cascade="all, delete-orphan", passive_deletes=True,
    )


class AssetContextLink(Base):
    """
    Relationship between an extraction asset and a related text passage.
    Built by the deterministic context linker (no LLM needed).
    """
    __tablename__ = "asset_context_links"

    id          = Column(Integer, primary_key=True, index=True)
    asset_id    = Column(Integer, ForeignKey("extraction_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    link_type   = Column(String, nullable=False)
    # caption | neighbor_before | neighbor_after | explicit_figure_reference | same_section | keyword_match
    text        = Column(Text, nullable=False)
    item_ref    = Column(String, nullable=True)
    page_number = Column(Integer, nullable=True)
    score       = Column(Float, default=1.0)
    created_at  = Column(DateTime, default=datetime.utcnow)

    asset = relationship("ExtractionAsset", back_populates="context_links")


# ════════════════════════════════════════════════════════════════════════════
# EXTERNAL REFERENCE DATA
# ════════════════════════════════════════════════════════════════════════════
# What PubChem and USDA add to an ingredient the corpus already named. Global, like the
# ingredients they hang off, and refreshed by a pass that is separate from ingestion so a
# rate-limited API can never fail a paper's extraction.

class IngredientMolecularFeature(Base):
    """Physicochemical description of one ingredient, from PubChem.

    Keyed on the ingredient rather than given its own id: an ingredient has at most one
    molecular description, and a separate primary key would permit two.

    `pka` is nullable more often than the rest because it is not a PUG-REST property at
    all -- it exists only as free text in the annotation view, and a value that does not
    parse is left null. Guessing a pKa is worse than not having one: it feeds a weighted
    mean that a food scientist then reads as evidence.
    """
    __tablename__ = "ingredient_molecular_features"

    ingredient_id    = Column(Integer, ForeignKey("ingredients.id", ondelete="CASCADE"), primary_key=True)
    smiles_code      = Column(String, nullable=True)
    molecular_weight = Column(Float, nullable=True)
    pka              = Column(Float, nullable=True)
    logp             = Column(Float, nullable=True)
    hbd_count        = Column(Integer, nullable=True)
    hba_count        = Column(Integer, nullable=True)
    source           = Column(String, nullable=True)    # see EXTERNAL_PROVIDERS
    external_id      = Column(String, nullable=True)    # PubChem CID
    fetched_at       = Column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("molecular_weight IS NULL OR molecular_weight > 0",
                        name="ck_molecular_weight_positive"),
        CheckConstraint("hbd_count IS NULL OR hbd_count >= 0", name="ck_hbd_non_negative"),
        CheckConstraint("hba_count IS NULL OR hba_count >= 0", name="ck_hba_non_negative"),
        CheckConstraint(f"source IS NULL OR source IN ({sql_values(EXTERNAL_PROVIDERS)})",
                        name="ck_molecular_features_source"),
    )


class IngredientRegulatoryStatus(Base):
    """Whether an ingredient is permitted, and up to what dose, in one jurisdiction.

    Hand-populated. There is no free machine-readable EU or FDA additive API worth wiring,
    and generating these from a model would produce authoritative-looking wrong limits --
    the one kind of error a food scientist has no way to catch downstream.
    """
    __tablename__ = "ingredient_regulatory_status"

    id             = Column(Integer, primary_key=True, index=True)
    ingredient_id  = Column(Integer, ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False, index=True)
    jurisdiction   = Column(String, nullable=False)     # e.g. "EU", "US"
    status         = Column(String, nullable=False)     # see REGULATORY_STATUSES
    max_dose_ppm   = Column(Float, nullable=True)
    reference      = Column(Text, nullable=True)        # the regulation this came from
    created_at     = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("ingredient_id", "jurisdiction", name="uq_regulatory_ingredient_jurisdiction"),
        CheckConstraint(f"status IN ({sql_values(REGULATORY_STATUSES)})",
                        name="ck_regulatory_status"),
        CheckConstraint("max_dose_ppm IS NULL OR max_dose_ppm >= 0",
                        name="ck_regulatory_max_dose_non_negative"),
    )


class IngredientExternalLookup(Base):
    """What one provider concluded about one ingredient, including that it knew nothing.

    This is the table that makes the enrichment pass idempotent. Without it a miss is
    indistinguishable from never having asked, so every run re-queries every unmatched
    ingredient -- which for a mixture like "thyme essential oil" is a request that can only
    ever fail. Recording `not_found` and `skipped` turns those into facts with a date on
    them, and `attempts` bounds the retries on a provider that is merely down.
    """
    __tablename__ = "ingredient_external_lookups"

    ingredient_id = Column(Integer, ForeignKey("ingredients.id", ondelete="CASCADE"), primary_key=True)
    provider      = Column(String, primary_key=True)    # see EXTERNAL_PROVIDERS
    status        = Column(String, nullable=False)      # see EXTERNAL_LOOKUP_STATUSES
    external_id   = Column(String, nullable=True)
    detail        = Column(Text, nullable=True)         # why it was skipped, or how it failed
    attempts      = Column(Integer, nullable=False, default=0, server_default="0")
    checked_at    = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(f"provider IN ({sql_values(EXTERNAL_PROVIDERS)})",
                        name="ck_external_lookup_provider"),
        CheckConstraint(f"status IN ({sql_values(EXTERNAL_LOOKUP_STATUSES)})",
                        name="ck_external_lookup_status"),
        CheckConstraint("attempts >= 0", name="ck_external_lookup_attempts_non_negative"),
    )
