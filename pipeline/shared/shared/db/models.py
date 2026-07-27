"""
SQLAlchemy ORM models for the Food Research Platform.

Hierarchy (canonical):
  Project → Study → Experiment → TreatmentArm → Observation
                              ↘ ExperimentMicroorganism → Microorganism

Supporting:
  Job, ExtractionRun, ExtractionChunk
  ProvenanceRecord, ValidationIssue, AuditEvent
  ProjectMember, ReviewAssignment, Comment
  NormalizationMapping
  TrajectoryDefinition, ModelRun, ModelFit, ModelPrediction
  ImputationProposal, ThresholdDefinition
  DatasetSnapshot, ExportRun

Legacy (preserved, never deleted):
  User, Project, Paper, ExtractedRow

Food-safety extraction schema (new):
  ExtIngredient, ExtExperiment, ExtExperimentIngredient,
  ExtIndicator, ExtMeasurement, ExtEvidence
"""

import json
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint, JSON,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


# ════════════════════════════════════════════════════════════════════════════
# LEGACY MODELS — unchanged, backward-compatible
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
    owner_id      = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner         = relationship("User", back_populates="projects")
    papers        = relationship("Paper", back_populates="project", cascade="all, delete-orphan")
    members       = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")
    studies       = relationship("Study", back_populates="project", cascade="all, delete-orphan")
    thresholds    = relationship("ThresholdDefinition", back_populates="project", cascade="all, delete-orphan")
    norm_mappings = relationship("NormalizationMapping", back_populates="project", cascade="all, delete-orphan")
    snapshots     = relationship("DatasetSnapshot", back_populates="project", cascade="all, delete-orphan")
    export_runs   = relationship("ExportRun", back_populates="project", cascade="all, delete-orphan")

    @property
    def schema(self):
        return json.loads(self.schema_json) if self.schema_json else []


class Paper(Base):
    __tablename__ = "papers"

    id            = Column(Integer, primary_key=True, index=True)
    project_id    = Column(Integer, ForeignKey("projects.id"), nullable=False)
    filename      = Column(String, nullable=False)
    original_name = Column(String, nullable=False)
    file_path     = Column(String, nullable=False)
    file_hash     = Column(String(64), index=True)   # SHA-256
    page_count    = Column(Integer, default=0)
    status        = Column(String, default="uploaded")
    error_message = Column(Text, default="")
    uploaded_at   = Column(DateTime, default=datetime.utcnow)

    project         = relationship("Project", back_populates="papers")
    rows            = relationship("ExtractedRow", back_populates="paper", cascade="all, delete-orphan")
    extraction_runs = relationship("ExtractionRun", back_populates="paper", cascade="all, delete-orphan")
    study           = relationship("Study", back_populates="paper", uselist=False)


class ExtractedRow(Base):
    """Legacy flat extracted row — preserved permanently, never auto-deleted."""
    __tablename__ = "extracted_rows"

    id              = Column(Integer, primary_key=True, index=True)
    paper_id        = Column(Integer, ForeignKey("papers.id"), nullable=False)
    project_id      = Column(Integer, ForeignKey("projects.id"), nullable=False)
    data_json       = Column(Text, default="{}")
    provenance_json = Column(Text, default="{}")
    status          = Column(String, default="pending")
    reviewer_note   = Column(Text, default="")
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Link to canonical entity if migrated
    canonical_study_id = Column(Integer, ForeignKey("studies.id"), nullable=True)

    paper = relationship("Paper", back_populates="rows")

    @property
    def data(self):
        return json.loads(self.data_json) if self.data_json else {}

    @property
    def provenance(self):
        return json.loads(self.provenance_json) if self.provenance_json else {}


# ════════════════════════════════════════════════════════════════════════════
# INFRASTRUCTURE: Jobs, ExtractionRuns, Chunks
# ════════════════════════════════════════════════════════════════════════════

class Job(Base):
    """Tracks all async work. Survives backend restarts via DB."""
    __tablename__ = "jobs"

    id              = Column(Integer, primary_key=True, index=True)
    project_id      = Column(Integer, ForeignKey("projects.id"), nullable=True)
    paper_id        = Column(Integer, ForeignKey("papers.id"), nullable=True)
    job_type        = Column(String, nullable=False)   # extraction|modelling|export|normalization
    status          = Column(String, default="queued") # queued|parsing|chunking|extracting_metadata|extracting_tables|extracting_observations|normalizing|validating|awaiting_review|completed|partial_success|failed|cancelled
    progress        = Column(Integer, default=0)        # 0-100
    current_step    = Column(String, default="")
    total_steps     = Column(Integer, default=0)
    error_message   = Column(Text, default="")
    result_json     = Column(Text, default="{}")
    idempotency_key = Column(String, unique=True, index=True, nullable=True)
    celery_task_id  = Column(String, index=True, nullable=True)
    created_by      = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    started_at      = Column(DateTime, nullable=True)
    completed_at    = Column(DateTime, nullable=True)

    extraction_run  = relationship("ExtractionRun", back_populates="job", uselist=False)

    @property
    def result(self):
        return json.loads(self.result_json) if self.result_json else {}


class ExtractionRun(Base):
    """One extraction attempt for one paper."""
    __tablename__ = "extraction_runs"

    id              = Column(Integer, primary_key=True, index=True)
    paper_id        = Column(Integer, ForeignKey("papers.id"), nullable=False)
    job_id          = Column(Integer, ForeignKey("jobs.id"), nullable=True)
    provider        = Column(String)        # vertexai|google_ai|openai|anthropic
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
    chunks = relationship("ExtractionChunk", back_populates="run", cascade="all, delete-orphan")


class ExtractionChunk(Base):
    """One page/section/table from a PDF during extraction."""
    __tablename__ = "extraction_chunks"

    id              = Column(Integer, primary_key=True, index=True)
    run_id          = Column(Integer, ForeignKey("extraction_runs.id"), nullable=False)
    chunk_type      = Column(String)   # page|section|table|figure_caption
    page_number     = Column(Integer)
    section_name    = Column(String)
    table_number    = Column(Integer, nullable=True)
    text_content    = Column(Text, default="")
    token_count     = Column(Integer, default=0)
    bbox_json       = Column(Text)   # [x0,y0,x1,y1]
    has_table       = Column(Boolean, default=False)
    table_json      = Column(Text)   # structured table data
    created_at      = Column(DateTime, default=datetime.utcnow)

    run = relationship("ExtractionRun", back_populates="chunks")


# ════════════════════════════════════════════════════════════════════════════
# CANONICAL SCIENTIFIC MODEL
# ════════════════════════════════════════════════════════════════════════════

class Study(Base):
    """One scientific paper/study. One-to-one with Paper (typically)."""
    __tablename__ = "studies"

    id                    = Column(Integer, primary_key=True, index=True)
    project_id            = Column(Integer, ForeignKey("projects.id"), nullable=False)
    paper_id              = Column(Integer, ForeignKey("papers.id"), nullable=True)
    title                 = Column(Text)
    authors_json          = Column(Text, default="[]")   # [str]
    publication_year      = Column(Integer)
    journal               = Column(String)
    doi_original          = Column(String)
    doi_normalized        = Column(String, index=True)
    country               = Column(String)
    study_type            = Column(String)   # challenge_study|shelf_life|in_vitro|in_vivo|field_study|review|other
    abstract              = Column(Text)
    notes                 = Column(Text, default="")
    review_status         = Column(String, default="extracted")   # extracted|needs_review|in_review|changes_requested|approved|rejected|superseded
    version               = Column(Integer, default=1)
    created_at            = Column(DateTime, default=datetime.utcnow)
    updated_at            = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by            = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by            = Column(Integer, ForeignKey("users.id"), nullable=True)
    legacy_row_id         = Column(Integer, ForeignKey("extracted_rows.id"), nullable=True)

    project       = relationship("Project", back_populates="studies")
    paper         = relationship("Paper", back_populates="study")
    experiments   = relationship("Experiment", back_populates="study", cascade="all, delete-orphan")
    provenance    = relationship("ProvenanceRecord", back_populates="study",
                                 primaryjoin="ProvenanceRecord.study_id == Study.id")
    # Comments are accessed via Comment.entity_type + entity_id query (polymorphic)
    # A direct relationship is omitted to avoid SQLAlchemy ambiguity warnings.

    __table_args__ = (
        Index("ix_study_project_doi", "project_id", "doi_normalized"),
    )

    @property
    def authors(self):
        return json.loads(self.authors_json) if self.authors_json else []


class Microorganism(Base):
    """Reusable taxonomy entity for microorganisms."""
    __tablename__ = "microorganisms"

    id              = Column(Integer, primary_key=True, index=True)
    project_id      = Column(Integer, ForeignKey("projects.id"), nullable=True)  # NULL = global
    genus           = Column(String, nullable=False)
    species         = Column(String)
    strain          = Column(String)
    original_text   = Column(String)   # as written in the paper
    canonical_name  = Column(String)   # genus species [strain]
    organism_role   = Column(String)   # pathogen|spoilage|starter|beneficial|indicator|unknown
    gram_category   = Column(String, nullable=True)  # positive|negative|variable — only if curated
    synonyms_json   = Column(Text, default="[]")
    notes           = Column(Text, default="")
    created_at      = Column(DateTime, default=datetime.utcnow)

    experiments     = relationship("ExperimentMicroorganism", back_populates="microorganism")
    observations    = relationship("Observation", back_populates="microorganism")

    @property
    def synonyms(self):
        return json.loads(self.synonyms_json) if self.synonyms_json else []


class Experiment(Base):
    """A set of shared experimental conditions within a study."""
    __tablename__ = "experiments"

    id                              = Column(Integer, primary_key=True, index=True)
    study_id                        = Column(Integer, ForeignKey("studies.id"), nullable=False)
    experiment_label                = Column(String)
    food_category                   = Column(String)   # cheese|meat|other
    product_name_original           = Column(String)
    product_name_normalized         = Column(String)
    product_family                  = Column(String)   # fresh|soft|semi-soft|semi-hard|hard|blue|brined|pasta-filata|processed|whey
    matrix_description              = Column(Text)
    milk_species                    = Column(String)   # cow|goat|sheep|buffalo|mixed
    milk_treatment                  = Column(String)   # raw|pasteurized|thermized
    fat_content_class               = Column(String)   # full-fat|reduced-fat|low-fat
    sampling_location               = Column(String)   # surface|rind|core|brine|whole|unknown
    storage_temperature_value       = Column(Float)
    storage_temperature_unit_original = Column(String)
    storage_temperature_c           = Column(Float)
    storage_relative_humidity       = Column(Float)
    packaging_type                  = Column(String)
    atmosphere_type                 = Column(String)   # aerobic|vacuum|MAP|anaerobic
    gas_composition_json            = Column(Text)     # {"O2": 0, "CO2": 30, "N2": 70}
    light_condition                 = Column(String)
    storage_duration_value          = Column(Float)
    storage_duration_unit_original  = Column(String)
    storage_duration_days           = Column(Float)
    study_design                    = Column(String)   # in_vitro|in_vivo|challenge_study|field_study|survey
    replicate_design                = Column(String)   # independent|technical
    artificial_inoculation          = Column(Boolean, nullable=True)
    initial_ph                      = Column(Float)
    initial_water_activity          = Column(Float)
    initial_salt_pct                = Column(Float)
    initial_moisture_pct            = Column(Float)
    extra_conditions_json           = Column(Text, default="{}")
    condition_signature             = Column(String, index=True)  # deterministic hash of normalized conditions
    review_status                   = Column(String, default="extracted")
    version                         = Column(Integer, default=1)
    created_at                      = Column(DateTime, default=datetime.utcnow)
    updated_at                      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by                      = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by                      = Column(Integer, ForeignKey("users.id"), nullable=True)

    study           = relationship("Study", back_populates="experiments")
    treatment_arms  = relationship("TreatmentArm", back_populates="experiment", cascade="all, delete-orphan")
    microorganisms  = relationship("ExperimentMicroorganism", back_populates="experiment", cascade="all, delete-orphan")
    trajectories    = relationship("TrajectoryDefinition", back_populates="experiment")

    @property
    def gas_composition(self):
        return json.loads(self.gas_composition_json) if self.gas_composition_json else {}

    @property
    def extra_conditions(self):
        return json.loads(self.extra_conditions_json) if self.extra_conditions_json else {}


class ExperimentMicroorganism(Base):
    """Many-to-many: Experiment ↔ Microorganism."""
    __tablename__ = "experiment_microorganisms"

    id               = Column(Integer, primary_key=True, index=True)
    experiment_id    = Column(Integer, ForeignKey("experiments.id"), nullable=False)
    microorganism_id = Column(Integer, ForeignKey("microorganisms.id"), nullable=False)
    role_in_study    = Column(String)  # target|indicator|background|contaminant
    inoculum_level   = Column(Float)
    inoculum_unit    = Column(String)

    experiment   = relationship("Experiment", back_populates="microorganisms")
    microorganism = relationship("Microorganism", back_populates="experiments")

    __table_args__ = (
        UniqueConstraint("experiment_id", "microorganism_id", name="uq_exp_micro"),
    )


class TreatmentArm(Base):
    """One control or treatment arm inside an experiment."""
    __tablename__ = "treatment_arms"

    id                          = Column(Integer, primary_key=True, index=True)
    experiment_id               = Column(Integer, ForeignKey("experiments.id"), nullable=False)
    arm_label                   = Column(String)
    is_control                  = Column(Boolean, default=False)
    control_arm_id              = Column(Integer, ForeignKey("treatment_arms.id"), nullable=True)
    treatment_type              = Column(String)   # antimicrobial|essential_oil|bacteriocin|packaging|temperature|combination|vehicle_control|untreated_control|other
    ingredient_name_original    = Column(String)
    ingredient_name_normalized  = Column(String)
    ingredient_source           = Column(String)
    ingredient_family           = Column(String)
    concentration_value_original = Column(Float)
    concentration_unit_original  = Column(String)
    concentration_value_normalized = Column(Float)
    concentration_unit_normalized  = Column(String)
    application_method          = Column(String)   # mixed|coating|spray|brine|packaging|surface|injection|dipping
    treatment_timing            = Column(String)   # pre-storage|during-storage|at-packaging|post-processing
    combination_treatments_json = Column(Text, default="[]")
    extra_treatment_json        = Column(Text, default="{}")
    review_status               = Column(String, default="extracted")
    version                     = Column(Integer, default=1)
    created_at                  = Column(DateTime, default=datetime.utcnow)
    updated_at                  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by                  = Column(Integer, ForeignKey("users.id"), nullable=True)

    experiment    = relationship("Experiment", back_populates="treatment_arms")
    control_arm   = relationship("TreatmentArm", remote_side="TreatmentArm.id", foreign_keys=[control_arm_id])
    observations  = relationship("Observation", back_populates="treatment_arm", cascade="all, delete-orphan")
    trajectories  = relationship("TrajectoryDefinition", back_populates="treatment_arm")

    @property
    def combination_treatments(self):
        return json.loads(self.combination_treatments_json) if self.combination_treatments_json else []

    @property
    def extra_treatment(self):
        return json.loads(self.extra_treatment_json) if self.extra_treatment_json else {}


class Observation(Base):
    """One measured value at one time point for one treatment arm."""
    __tablename__ = "observations"

    id                      = Column(Integer, primary_key=True, index=True)
    treatment_arm_id        = Column(Integer, ForeignKey("treatment_arms.id"), nullable=False)
    microorganism_id        = Column(Integer, ForeignKey("microorganisms.id"), nullable=True)

    measurement_type        = Column(String, nullable=False)  # microbial_count|ph|water_activity|moisture|color_L|color_a|color_b|texture|TBARS|TBA|PV|TVB_N|sensory|protein|weight_loss|shelf_life|threshold_crossing|other
    measurement_subtype     = Column(String)   # e.g. aerobic_plate_count|yeast_mold|Listeria
    measurement_unit_normalized = Column(String)  # canonical unit for this type

    time_value_original     = Column(Float)
    time_unit_original      = Column(String)
    time_days               = Column(Float)     # always in days, normalized

    value_original_text     = Column(String)    # raw string from paper (e.g. "3.2 ± 0.4")
    numeric_value_original  = Column(Float)
    unit_original           = Column(String)
    numeric_value_normalized = Column(Float)
    unit_normalized         = Column(String)

    mean_value              = Column(Float)
    standard_deviation      = Column(Float)
    standard_error          = Column(Float)
    minimum_value           = Column(Float)
    maximum_value           = Column(Float)
    replicate_count         = Column(Integer)
    detection_limit         = Column(Float)
    detection_limit_unit    = Column(String)

    # Missingness and censoring
    censoring_type          = Column(String, default="none")  # none|left|right|interval
    value_origin            = Column(String, default="reported_table")  # reported_table|reported_text|reported_figure|graph_estimated|calculated|unit_converted|normalized|model_imputed|manual_entry|imported_external|synthetic
    missing_reason          = Column(String, nullable=True)   # not_reported|not_measured|not_applicable|below_detection_limit|above_detection_limit|unreadable_source|extraction_failed|removed_after_validation|figure_only_not_digitized|intentionally_masked_for_validation|unknown
    is_imputed              = Column(Boolean, default=False)
    is_derived              = Column(Boolean, default=False)
    significance_letter     = Column(String)   # e.g. "a" from statistical significance grouping

    quality_score           = Column(Float)    # 0-1
    review_status           = Column(String, default="extracted")
    version                 = Column(Integer, default=1)
    created_at              = Column(DateTime, default=datetime.utcnow)
    updated_at              = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by              = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by              = Column(Integer, ForeignKey("users.id"), nullable=True)
    extraction_run_id       = Column(Integer, ForeignKey("extraction_runs.id"), nullable=True)
    chunk_id                = Column(Integer, ForeignKey("extraction_chunks.id"), nullable=True)

    treatment_arm   = relationship("TreatmentArm", back_populates="observations")
    microorganism   = relationship("Microorganism", back_populates="observations")
    provenance      = relationship("ProvenanceRecord", back_populates="observation",
                                    primaryjoin="ProvenanceRecord.observation_id == Observation.id")
    validation_issues = relationship("ValidationIssue", back_populates="observation",
                                      primaryjoin="ValidationIssue.observation_id == Observation.id")

    __table_args__ = (
        Index("ix_obs_arm_time", "treatment_arm_id", "time_days"),
        Index("ix_obs_type", "measurement_type"),
    )


# ════════════════════════════════════════════════════════════════════════════
# EVIDENCE AND QUALITY
# ════════════════════════════════════════════════════════════════════════════

class ProvenanceRecord(Base):
    """Field- or observation-level PDF evidence."""
    __tablename__ = "provenance_records"

    id                  = Column(Integer, primary_key=True, index=True)
    # Target entity (polymorphic)
    entity_type         = Column(String, nullable=False)  # study|experiment|treatment_arm|observation
    entity_id           = Column(Integer, nullable=False, index=True)
    study_id            = Column(Integer, ForeignKey("studies.id"), nullable=True)
    observation_id      = Column(Integer, ForeignKey("observations.id"), nullable=True)
    field_name          = Column(String)     # which specific field this provenance covers
    paper_id            = Column(Integer, ForeignKey("papers.id"), nullable=False)
    page_number         = Column(Integer)
    page_label          = Column(String)    # e.g. "S3" for supplementary
    section_name        = Column(String)
    table_number        = Column(Integer, nullable=True)
    figure_number       = Column(Integer, nullable=True)
    table_row_header    = Column(String)
    table_col_header    = Column(String)
    source_snippet      = Column(Text)      # exact text from PDF
    bbox_x0             = Column(Float)
    bbox_y0             = Column(Float)
    bbox_x1             = Column(Float)
    bbox_y1             = Column(Float)
    extraction_provider = Column(String)
    extraction_model    = Column(String)
    prompt_version      = Column(String)
    extraction_run_id   = Column(Integer, ForeignKey("extraction_runs.id"), nullable=True)
    confidence          = Column(Float)     # 0-1
    manually_verified   = Column(Boolean, default=False)
    verified_by         = Column(Integer, ForeignKey("users.id"), nullable=True)
    verified_at         = Column(DateTime, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)

    study       = relationship("Study", back_populates="provenance", foreign_keys=[study_id])
    observation = relationship("Observation", back_populates="provenance", foreign_keys=[observation_id])


class ValidationIssue(Base):
    """A scientific validation rule violation."""
    __tablename__ = "validation_issues"

    id               = Column(Integer, primary_key=True, index=True)
    entity_type      = Column(String)     # study|experiment|treatment_arm|observation
    entity_id        = Column(Integer, index=True)
    observation_id   = Column(Integer, ForeignKey("observations.id"), nullable=True)
    field_name       = Column(String)
    rule_code        = Column(String, index=True)  # stable code e.g. "VAL-001"
    severity         = Column(String)              # error|warning|info
    message          = Column(Text)
    detected_value   = Column(String)
    expected_condition = Column(String)
    remediation_hint = Column(Text)
    resolved         = Column(Boolean, default=False)
    resolution_note  = Column(Text)
    resolved_by      = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at      = Column(DateTime, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)

    observation = relationship("Observation", back_populates="validation_issues", foreign_keys=[observation_id])


class AuditEvent(Base):
    """Immutable record of every create/update/delete/approve/reject action."""
    __tablename__ = "audit_events"

    id            = Column(Integer, primary_key=True, index=True)
    actor_id      = Column(Integer, ForeignKey("users.id"), nullable=True)
    entity_type   = Column(String, nullable=False, index=True)
    entity_id     = Column(Integer, nullable=False, index=True)
    action        = Column(String, nullable=False)  # create|update|delete|approve|reject|normalize|impute|import|export
    before_json   = Column(Text)
    after_json    = Column(Text)
    diff_json     = Column(Text)    # only changed fields
    reason        = Column(Text)
    source        = Column(String)  # user|ai_extraction|normalizer|model|import
    ip_address    = Column(String)
    project_id    = Column(Integer, ForeignKey("projects.id"), nullable=True)
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
    project_id  = Column(Integer, ForeignKey("projects.id"), nullable=False)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    role        = Column(String, nullable=False)   # owner|admin|reviewer|analyst|viewer
    invited_by  = Column(Integer, ForeignKey("users.id"), nullable=True)
    joined_at   = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="members")
    user    = relationship("User", back_populates="project_members", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_member"),
    )


class ReviewAssignment(Base):
    """Assigns a paper/study to a specific reviewer."""
    __tablename__ = "review_assignments"

    id              = Column(Integer, primary_key=True, index=True)
    project_id      = Column(Integer, ForeignKey("projects.id"), nullable=False)
    study_id        = Column(Integer, ForeignKey("studies.id"), nullable=True)
    paper_id        = Column(Integer, ForeignKey("papers.id"), nullable=True)
    reviewer_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_by     = Column(Integer, ForeignKey("users.id"), nullable=True)
    status          = Column(String, default="pending")   # pending|in_progress|completed|reassigned
    due_date        = Column(DateTime, nullable=True)
    completed_at    = Column(DateTime, nullable=True)
    notes           = Column(Text)
    created_at      = Column(DateTime, default=datetime.utcnow)


class Comment(Base):
    """Threaded comments on any entity."""
    __tablename__ = "comments"

    id          = Column(Integer, primary_key=True, index=True)
    project_id  = Column(Integer, ForeignKey("projects.id"), nullable=True)
    entity_type = Column(String, nullable=False)   # study|experiment|treatment_arm|observation|row
    entity_id   = Column(Integer, nullable=False, index=True)
    parent_id   = Column(Integer, ForeignKey("comments.id"), nullable=True)
    author_id   = Column(Integer, ForeignKey("users.id"), nullable=False)
    body        = Column(Text, nullable=False)
    resolved    = Column(Boolean, default=False)
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    replies = relationship("Comment", back_populates="parent")
    parent  = relationship("Comment", back_populates="replies", remote_side="Comment.id")


# ════════════════════════════════════════════════════════════════════════════
# NORMALIZATION
# ════════════════════════════════════════════════════════════════════════════

class NormalizationMapping(Base):
    """Maps an original term → canonical term for a given field type."""
    __tablename__ = "normalization_mappings"

    id              = Column(Integer, primary_key=True, index=True)
    project_id      = Column(Integer, ForeignKey("projects.id"), nullable=True)  # NULL = global
    mapping_type    = Column(String, nullable=False)   # microorganism|ingredient|cheese_type|packaging|application_method|unit|measurement_type
    original_term   = Column(String, nullable=False)
    canonical_term  = Column(String, nullable=False)
    canonical_id    = Column(Integer, nullable=True)  # FK to canonical entity if applicable
    confidence      = Column(Float, default=1.0)
    source          = Column(String)   # manual|ai_suggested|imported
    created_by      = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    applied_count   = Column(Integer, default=0)

    project = relationship("Project", back_populates="norm_mappings")

    __table_args__ = (
        UniqueConstraint("project_id", "mapping_type", "original_term", name="uq_norm_mapping"),
    )


# ════════════════════════════════════════════════════════════════════════════
# TRAJECTORIES AND MODELS
# ════════════════════════════════════════════════════════════════════════════

class TrajectoryDefinition(Base):
    """Defines a compatible group of observations forming a temporal series."""
    __tablename__ = "trajectory_definitions"

    id                  = Column(Integer, primary_key=True, index=True)
    project_id          = Column(Integer, ForeignKey("projects.id"), nullable=False)
    experiment_id       = Column(Integer, ForeignKey("experiments.id"), nullable=True)
    treatment_arm_id    = Column(Integer, ForeignKey("treatment_arms.id"), nullable=True)
    label               = Column(String)
    measurement_type    = Column(String, nullable=False)
    measurement_subtype = Column(String)
    microorganism_id    = Column(Integer, ForeignKey("microorganisms.id"), nullable=True)
    process_class       = Column(String)  # growth|inactivation|stable|monotonic_increase|monotonic_decrease|non_monotonic|insufficient_data
    grouping_signature  = Column(String, index=True)  # deterministic hash
    observation_ids_json = Column(Text, default="[]")  # [int]
    n_points            = Column(Integer, default=0)
    time_min_days       = Column(Float)
    time_max_days       = Column(Float)
    has_control         = Column(Boolean, default=False)
    data_sufficient     = Column(Boolean, default=False)  # meets minimum data requirements
    notes               = Column(Text)
    created_by          = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    experiment    = relationship("Experiment", back_populates="trajectories")
    treatment_arm = relationship("TreatmentArm", back_populates="trajectories")
    model_runs    = relationship("ModelRun", back_populates="trajectory")

    @property
    def observation_ids(self):
        return json.loads(self.observation_ids_json) if self.observation_ids_json else []


class ModelRun(Base):
    """One attempt to fit all eligible models to a trajectory."""
    __tablename__ = "model_runs"

    id                  = Column(Integer, primary_key=True, index=True)
    trajectory_id       = Column(Integer, ForeignKey("trajectory_definitions.id"), nullable=False)
    project_id          = Column(Integer, ForeignKey("projects.id"), nullable=False)
    status              = Column(String, default="pending")  # pending|running|completed|failed
    models_tried        = Column(Integer, default=0)
    models_converged    = Column(Integer, default=0)
    selected_model_id   = Column(Integer, ForeignKey("model_fits.id"), nullable=True)
    error_message       = Column(Text)
    created_by          = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    completed_at        = Column(DateTime, nullable=True)

    trajectory    = relationship("TrajectoryDefinition", back_populates="model_runs")
    fits          = relationship("ModelFit", back_populates="run",
                                  foreign_keys="ModelFit.run_id")
    selected_model = relationship("ModelFit", foreign_keys=[selected_model_id])


class ModelFit(Base):
    """Fitted parameters and metrics for one model on one trajectory."""
    __tablename__ = "model_fits"

    id                  = Column(Integer, primary_key=True, index=True)
    run_id              = Column(Integer, ForeignKey("model_runs.id"), nullable=False)
    model_name          = Column(String, nullable=False)   # Gompertz|Baranyi|Logistic|Weibull|Geeraerd|etc.
    model_version       = Column(String)
    process_class       = Column(String)
    converged           = Column(Boolean, default=False)
    convergence_message = Column(String)
    parameters_json     = Column(Text, default="{}")   # {param_name: value}
    parameter_bounds_json = Column(Text, default="{}")
    parameter_se_json   = Column(Text, default="{}")   # standard errors
    mae                 = Column(Float)
    rmse                = Column(Float)
    r_squared           = Column(Float)
    adjusted_r_squared  = Column(Float)
    aic                 = Column(Float)
    bic                 = Column(Float)
    aicc                = Column(Float)
    residual_bias       = Column(Float)
    loo_mae             = Column(Float)    # leave-one-out
    loo_rmse            = Column(Float)
    biological_violations = Column(Integer, default=0)
    applicability_status = Column(String)  # green|yellow|red
    applicability_reasons_json = Column(Text, default="[]")
    rank                = Column(Integer)   # 1 = best
    equation_text       = Column(Text)
    created_at          = Column(DateTime, default=datetime.utcnow)

    run         = relationship("ModelRun", back_populates="fits", foreign_keys=[run_id])
    predictions = relationship("ModelPrediction", back_populates="fit", cascade="all, delete-orphan")

    @property
    def parameters(self):
        return json.loads(self.parameters_json) if self.parameters_json else {}

    @property
    def parameter_se(self):
        return json.loads(self.parameter_se_json) if self.parameter_se_json else {}

    @property
    def applicability_reasons(self):
        return json.loads(self.applicability_reasons_json) if self.applicability_reasons_json else []


class ModelPrediction(Base):
    """Predicted values from a ModelFit at specified time points."""
    __tablename__ = "model_predictions"

    id              = Column(Integer, primary_key=True, index=True)
    fit_id          = Column(Integer, ForeignKey("model_fits.id"), nullable=False)
    time_days       = Column(Float, nullable=False)
    predicted_value = Column(Float)
    lower_bound     = Column(Float)
    upper_bound     = Column(Float)
    interval_type   = Column(String)   # confidence|prediction|bootstrap
    interval_level  = Column(Float, default=0.95)
    is_interpolation = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.utcnow)

    fit = relationship("ModelFit", back_populates="predictions")


# ════════════════════════════════════════════════════════════════════════════
# IMPUTATION
# ════════════════════════════════════════════════════════════════════════════

class ImputationProposal(Base):
    """A proposed imputed value — NEVER overwrites observed data."""
    __tablename__ = "imputation_proposals"

    id                      = Column(Integer, primary_key=True, index=True)
    project_id              = Column(Integer, ForeignKey("projects.id"), nullable=False)
    trajectory_id           = Column(Integer, ForeignKey("trajectory_definitions.id"), nullable=True)
    fit_id                  = Column(Integer, ForeignKey("model_fits.id"), nullable=True)
    target_observation_id   = Column(Integer, ForeignKey("observations.id"), nullable=True)
    target_arm_id           = Column(Integer, ForeignKey("treatment_arms.id"), nullable=True)
    target_time_days        = Column(Float)
    target_measurement_type = Column(String)
    predicted_value         = Column(Float)
    lower_bound             = Column(Float)
    upper_bound             = Column(Float)
    interval_type           = Column(String)
    is_interpolation        = Column(Boolean, default=True)
    extrapolation_days      = Column(Float, default=0.0)
    applicability_status    = Column(String)    # green|yellow|red
    applicability_reasons_json = Column(Text, default="[]")
    cross_validation_mae    = Column(Float)
    cross_validation_rmse   = Column(Float)
    n_points_used           = Column(Integer)
    model_name              = Column(String)
    parameters_json         = Column(Text, default="{}")
    # Review
    reviewer_decision       = Column(String)    # pending|accepted|rejected|superseded
    reviewer_id             = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewer_note           = Column(Text)
    reviewed_at             = Column(DateTime, nullable=True)
    created_by              = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at              = Column(DateTime, default=datetime.utcnow)

    @property
    def applicability_reasons(self):
        return json.loads(self.applicability_reasons_json) if self.applicability_reasons_json else []

    @property
    def parameters(self):
        return json.loads(self.parameters_json) if self.parameters_json else {}


# ════════════════════════════════════════════════════════════════════════════
# THRESHOLDS
# ════════════════════════════════════════════════════════════════════════════

class ThresholdDefinition(Base):
    """A scientific/regulatory limit for a measurement type."""
    __tablename__ = "threshold_definitions"

    id                  = Column(Integer, primary_key=True, index=True)
    project_id          = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name                = Column(String, nullable=False)
    measurement_type    = Column(String, nullable=False)
    threshold_value     = Column(Float, nullable=False)
    threshold_unit      = Column(String)
    comparison_operator = Column(String, default="<=")   # <= | >= | < | >
    product_scope       = Column(String)    # cheese family or product name or null for all
    microorganism_scope = Column(String)    # organism or null for all
    source_type         = Column(String)    # paper|regulation|team_defined|external_reference
    source_citation     = Column(Text)
    notes               = Column(Text)
    is_active           = Column(Boolean, default=True)
    version             = Column(Integer, default=1)
    created_by          = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="thresholds")


# ════════════════════════════════════════════════════════════════════════════
# EXPORT AND SNAPSHOTS
# ════════════════════════════════════════════════════════════════════════════

class DatasetSnapshot(Base):
    """Versioned, reproducible dataset export."""
    __tablename__ = "dataset_snapshots"

    id              = Column(Integer, primary_key=True, index=True)
    project_id      = Column(Integer, ForeignKey("projects.id"), nullable=False)
    label           = Column(String)
    description     = Column(Text)
    filters_json    = Column(Text, default="{}")    # what filters were applied
    row_count       = Column(Integer, default=0)
    observation_count = Column(Integer, default=0)
    includes_imputed = Column(Boolean, default=False)
    only_approved   = Column(Boolean, default=True)
    feature_config_json = Column(Text, default="{}")
    snapshot_hash   = Column(String(64))   # SHA-256 of snapshot content
    created_by      = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="snapshots")

    @property
    def filters(self):
        return json.loads(self.filters_json) if self.filters_json else {}

    @property
    def feature_config(self):
        return json.loads(self.feature_config_json) if self.feature_config_json else {}


class ExportRun(Base):
    """Tracks an export generation job."""
    __tablename__ = "export_runs"

    id              = Column(Integer, primary_key=True, index=True)
    project_id      = Column(Integer, ForeignKey("projects.id"), nullable=False)
    snapshot_id     = Column(Integer, ForeignKey("dataset_snapshots.id"), nullable=True)
    format          = Column(String)    # excel|csv_zip|json|parquet
    status          = Column(String, default="pending")
    file_path       = Column(String)
    file_size_bytes = Column(Integer)
    filters_json    = Column(Text, default="{}")
    created_by      = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    completed_at    = Column(DateTime, nullable=True)
    error_message   = Column(Text)

    project = relationship("Project", back_populates="export_runs")


# ─────────────────────────────────────────────────────────────────────────────
# MODEL LAB — uploaded training datasets, training runs, trained model results
# ─────────────────────────────────────────────────────────────────────────────

class UploadedDataset(Base):
    """A CSV or XLSX file uploaded by the user for model training."""
    __tablename__ = "uploaded_datasets"

    id                  = Column(Integer, primary_key=True, index=True)
    project_id          = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    uploader_id         = Column(Integer, ForeignKey("users.id"), nullable=True)

    original_name       = Column(String, nullable=False)       # user-facing filename
    filename            = Column(String, nullable=False)        # UUID-based stored name
    file_path           = Column(String, nullable=False)        # absolute server path
    file_hash           = Column(String(64), nullable=True, index=True)  # SHA-256

    sheet_name          = Column(String, nullable=True)         # first sheet for Excel
    dataset_family      = Column(String, nullable=True)         # kinetic | survival
    row_count           = Column(Integer, default=0)
    col_count           = Column(Integer, default=0)
    headers_json        = Column(Text, default="[]")            # JSON list of column names
    column_types_json   = Column(Text, default="{}")            # {col: numeric|boolean|...}
    column_mapping_json = Column(Text, default="{}")            # {col: role_id}

    parse_status        = Column(String, default="pending")     # pending|ready|error
    parse_error         = Column(Text, nullable=True)
    is_active           = Column(Boolean, default=True)         # False = soft-deleted

    uploaded_at         = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LabTrainingRun(Base):
    """One training invocation against an UploadedDataset."""
    __tablename__ = "lab_training_runs"

    id                  = Column(Integer, primary_key=True, index=True)
    project_id          = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    dataset_id          = Column(Integer, ForeignKey("uploaded_datasets.id"), nullable=False)
    job_id              = Column(Integer, ForeignKey("jobs.id"), nullable=True, index=True)

    dataset_family      = Column(String, nullable=False)
    column_mapping_json = Column(Text, default="{}")
    dataset_hash        = Column(String(64), nullable=True)

    n_trajectories      = Column(Integer, default=0)
    n_fitted            = Column(Integer, default=0)

    status              = Column(String, default="queued")      # queued|running|completed|failed
    error_message       = Column(Text, nullable=True)

    created_by          = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    completed_at        = Column(DateTime, nullable=True)


class LabModelResult(Base):
    """Result for one model type within a LabTrainingRun."""
    __tablename__ = "lab_model_results"

    id                  = Column(Integer, primary_key=True, index=True)
    training_run_id     = Column(Integer, ForeignKey("lab_training_runs.id"), nullable=False, index=True)
    project_id          = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)

    model_name          = Column(String, nullable=False)        # baranyi | gompertz | weibull_aft | ...
    model_family        = Column(String, nullable=False)        # kinetic | survival
    status              = Column(String, default="pending")     # pending|training|completed|failed|skipped
    skip_reason         = Column(Text, nullable=True)
    error_message       = Column(Text, nullable=True)

    results_json        = Column(Text, default="{}")            # per-trajectory or global results
    metrics_json        = Column(Text, default="{}")            # aggregate metrics
    parameters_json     = Column(Text, default="{}")            # fitted parameter summary

    artifact_path       = Column(String, nullable=True)         # joblib model file
    preprocessing_path  = Column(String, nullable=True)         # preprocessing pipeline

    feature_cols_json   = Column(Text, default="[]")
    target_col          = Column(String, nullable=True)
    event_col           = Column(String, nullable=True)

    # Summary metrics (redundant with metrics_json for quick queries)
    mae                 = Column(Float, nullable=True)
    rmse                = Column(Float, nullable=True)
    r_squared           = Column(Float, nullable=True)
    concordance_index   = Column(Float, nullable=True)

    is_active           = Column(Boolean, default=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    completed_at        = Column(DateTime, nullable=True)


# ─── Food-Safety Extraction Schema ────────────────────────────────────────────
# Targeted tables extracted by the new Llama 4 pipeline.
# The ext_ prefix avoids conflicts with the legacy canonical hierarchy.

class ExtIngredient(Base):
    """Reusable ingredient catalogue — one row per unique ingredient name per project."""
    __tablename__ = "ext_ingredients"

    id                  = Column(Integer, primary_key=True, index=True)
    project_id          = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    ingredient_name     = Column(String, nullable=False)
    functional_class    = Column(String, nullable=False)   # antimicrobial | antioxidant | ...
    source              = Column(String, nullable=False)   # biological origin, NOT paper
    created_at          = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("project_id", "ingredient_name", name="uq_ext_ing_proj_name"),)


class ExtExperiment(Base):
    """One row per distinct (meat_matrix, treatment) combination in a paper."""
    __tablename__ = "ext_experiments"

    id                  = Column(Integer, primary_key=True, index=True)
    project_id          = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    paper_id            = Column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id              = Column(Integer, ForeignKey("jobs.id"), nullable=True)
    meat_matrix         = Column(String, nullable=False)
    treatment           = Column(String, nullable=False)
    created_at          = Column(DateTime, default=datetime.utcnow)


class ExtExperimentIngredient(Base):
    """Junction: many experiments ↔ many ingredients, with concentration."""
    __tablename__ = "ext_experiment_ingredients"

    experiment_id       = Column(Integer, ForeignKey("ext_experiments.id", ondelete="CASCADE"), primary_key=True)
    ingredient_id       = Column(Integer, ForeignKey("ext_ingredients.id", ondelete="CASCADE"), primary_key=True)
    concentration       = Column(Float, nullable=False)
    concentration_unit  = Column(String, nullable=False)


class ExtIndicator(Base):
    """Reusable indicator catalogue — one row per unique (type, unit) per project."""
    __tablename__ = "ext_indicators"

    id                  = Column(Integer, primary_key=True, index=True)
    project_id          = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    indicator_type      = Column(String, nullable=False)   # e.g. "Total viable count"
    indicator_unit      = Column(String, nullable=False)   # e.g. "log CFU/g"
    indicator_threshold = Column(Float, nullable=True)     # e.g. 7 (regulatory limit)
    created_at          = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("project_id", "indicator_type", "indicator_unit",
                                       name="uq_ext_ind_proj_type_unit"),)


class ExtMeasurement(Base):
    """One value per (experiment, day, indicator) — composite primary key."""
    __tablename__ = "ext_measurements"

    experiment_id       = Column(Integer, ForeignKey("ext_experiments.id", ondelete="CASCADE"), primary_key=True)
    day                 = Column(Integer, primary_key=True)
    indicator_id        = Column(Integer, ForeignKey("ext_indicators.id", ondelete="CASCADE"), primary_key=True)
    indicator_value     = Column(Float, nullable=False)
    value_is_approximate = Column(Boolean, default=False)


class ExtEvidence(Base):
    """Row-level evidence linking extracted values to exact PDF locations."""
    __tablename__ = "ext_evidence"

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
    # Docling provenance anchor — set by the new extraction pipeline
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
        "FigureConversionCache", back_populates="docling_cache", cascade="all, delete-orphan"
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
    job_id              = Column(Integer, ForeignKey("jobs.id"), nullable=True)
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
        "AssetContextLink", back_populates="asset", cascade="all, delete-orphan"
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
