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
  Job, ExtractionRun          async work and its audit trail
  AuditEvent                  immutable action log
  ProjectMember               team roles
  DoclingCache, FigureConversionCache     parse/chart-conversion caches, keyed by file hash
  ExtractionAsset, AssetContextLink       the extraction workspace (figures, tables, charts)

Platform:
  User, Project, Paper

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
    Boolean, Column, DateTime, Float, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from shared.db.database import Base


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

    project         = relationship("Project", back_populates="papers")
    extraction_runs = relationship("ExtractionRun", back_populates="paper", cascade="all, delete-orphan", passive_deletes=True)
    # No cascade: jobs are the async audit trail and outlive the paper they ran on
    # (`jobs.paper_id` is ON DELETE SET NULL). This relationship exists so the ORM is aware
    # of the table at all -- its absence is what made deleting a paper fail on the FK.
    jobs            = relationship("Job", back_populates="paper", passive_deletes=True)


# ════════════════════════════════════════════════════════════════════════════
# INFRASTRUCTURE: Jobs and extraction runs
# ════════════════════════════════════════════════════════════════════════════

class Job(Base):
    """Tracks all async work. Survives backend restarts via DB."""
    __tablename__ = "jobs"

    id              = Column(Integer, primary_key=True, index=True)
    project_id      = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    paper_id        = Column(Integer, ForeignKey("papers.id", ondelete="SET NULL"), nullable=True)
    job_type        = Column(String, nullable=False)   # workspace_extraction|llm_ingestion|dataset_build
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

class Ingredient(Base):
    """Reusable ingredient catalogue — one row per unique ingredient name per project."""
    __tablename__ = "ingredients"

    id                  = Column(Integer, primary_key=True, index=True)
    project_id          = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    ingredient_name     = Column(String, nullable=False)
    functional_class    = Column(String, nullable=False)   # antimicrobial | antioxidant | ...
    source              = Column(String, nullable=False)   # biological origin, NOT paper
    created_at          = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("project_id", "ingredient_name", name="uq_ingredient_project_name"),
    )


class Experiment(Base):
    """One row per distinct (meat_matrix, treatment) combination in a paper."""
    __tablename__ = "experiments"

    id                  = Column(Integer, primary_key=True, index=True)
    project_id          = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    paper_id            = Column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id              = Column(Integer, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    meat_matrix         = Column(String, nullable=False)
    treatment           = Column(String, nullable=False)
    created_at          = Column(DateTime, default=datetime.utcnow)


class ExperimentIngredient(Base):
    """Junction: many experiments ↔ many ingredients, with concentration."""
    __tablename__ = "experiment_ingredients"

    experiment_id       = Column(Integer, ForeignKey("experiments.id", ondelete="CASCADE"), primary_key=True)
    ingredient_id       = Column(Integer, ForeignKey("ingredients.id", ondelete="CASCADE"), primary_key=True)
    concentration       = Column(Float, nullable=False)
    concentration_unit  = Column(String, nullable=False)


class Indicator(Base):
    """Reusable indicator catalogue — one row per unique (type, unit) per project.

    `indicator_threshold` is the scientific or regulatory limit for the indicator: the
    value a measurement crosses to end shelf life. It is what a survival label is derived
    from, which is why it lives here rather than in a separate definitions table -- a
    threshold with no indicator to apply it to means nothing.
    """
    __tablename__ = "indicators"

    id                  = Column(Integer, primary_key=True, index=True)
    project_id          = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    indicator_type      = Column(String, nullable=False)   # e.g. "Total viable count"
    indicator_unit      = Column(String, nullable=False)   # e.g. "log CFU/g"
    indicator_threshold = Column(Float, nullable=True)     # e.g. 7 (regulatory limit)
    created_at          = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("project_id", "indicator_type", "indicator_unit",
                         name="uq_indicator_project_type_unit"),
    )


class Measurement(Base):
    """One value per (experiment, day, indicator) — composite primary key."""
    __tablename__ = "measurements"

    experiment_id       = Column(Integer, ForeignKey("experiments.id", ondelete="CASCADE"), primary_key=True)
    day                 = Column(Integer, primary_key=True)
    indicator_id        = Column(Integer, ForeignKey("indicators.id", ondelete="CASCADE"), primary_key=True)
    indicator_value     = Column(Float, nullable=False)
    value_is_approximate = Column(Boolean, default=False)


class Evidence(Base):
    """Row-level evidence linking extracted values to exact PDF locations."""
    __tablename__ = "evidence"

    id                  = Column(Integer, primary_key=True, index=True)
    paper_id            = Column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type         = Column(String, nullable=False)   # experiment|ingredient_link|measurement
    # Composite entity key stored as JSON string, e.g. '{"experiment_id":5,"day":3,"indicator_id":2}'
    entity_key          = Column(Text, nullable=False)
    field_name          = Column(String, nullable=True)    # specific field this evidence supports
    page_number         = Column(Integer, nullable=True)
    source_type         = Column(String, nullable=False)   # text|table|chart|figure|caption|supplementary_material
    source_label        = Column(String, nullable=True)    # "Table 2", "Figure 3", ...
    exact_text          = Column(Text, nullable=True)
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
