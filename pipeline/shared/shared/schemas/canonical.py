"""
Pydantic v2 schemas for all canonical scientific entities.

Convention:
  - *Create  — input for POST (no id, no server-set timestamps)
  - *Update  — input for PATCH  (all fields Optional)
  - *Out     — response (includes id, timestamps, computed fields)
  - *Brief   — lightweight response used in list endpoints
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ─── shared config ────────────────────────────────────────────────────────────
_ORM = ConfigDict(from_attributes=True)


# ════════════════════════════════════════════════════════════════════════════
# USERS (thin read-only view, auth schemas live in auth.py)
# ════════════════════════════════════════════════════════════════════════════

class UserBrief(BaseModel):
    model_config = _ORM
    id: int
    email: str
    full_name: str


# ════════════════════════════════════════════════════════════════════════════
# JOBS
# ════════════════════════════════════════════════════════════════════════════

class JobOut(BaseModel):
    model_config = _ORM

    id: int
    project_id: Optional[int]
    paper_id: Optional[int]
    job_type: str
    status: str
    progress: int
    current_step: str
    total_steps: int
    error_message: str
    result: dict[str, Any]
    celery_task_id: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


# ════════════════════════════════════════════════════════════════════════════
# EXTRACTION RUNS
# ════════════════════════════════════════════════════════════════════════════

class ExtractionRunOut(BaseModel):
    model_config = _ORM

    id: int
    paper_id: int
    job_id: Optional[int]
    provider: Optional[str]
    model_name: Optional[str]
    prompt_version: Optional[str]
    status: str
    pages_processed: int
    chunks_created: int
    rows_extracted: int
    tables_found: int
    error_message: str
    created_at: datetime
    completed_at: Optional[datetime]


# ════════════════════════════════════════════════════════════════════════════
# MICROORGANISMS
# ════════════════════════════════════════════════════════════════════════════

class MicroorganismCreate(BaseModel):
    genus: str
    species: Optional[str] = None
    strain: Optional[str] = None
    original_text: Optional[str] = None
    canonical_name: Optional[str] = None
    organism_role: Optional[str] = "unknown"
    gram_category: Optional[str] = None
    synonyms: list[str] = Field(default_factory=list)
    notes: Optional[str] = ""
    project_id: Optional[int] = None

    @model_validator(mode="after")
    def build_canonical_name(self) -> MicroorganismCreate:
        if not self.canonical_name:
            parts = [self.genus]
            if self.species:
                parts.append(self.species)
            if self.strain:
                parts.append(f"[{self.strain}]")
            self.canonical_name = " ".join(parts)
        return self


class MicroorganismUpdate(BaseModel):
    genus: Optional[str] = None
    species: Optional[str] = None
    strain: Optional[str] = None
    canonical_name: Optional[str] = None
    organism_role: Optional[str] = None
    gram_category: Optional[str] = None
    synonyms: Optional[list[str]] = None
    notes: Optional[str] = None


class MicroorganismOut(BaseModel):
    model_config = _ORM

    id: int
    project_id: Optional[int]
    genus: str
    species: Optional[str]
    strain: Optional[str]
    original_text: Optional[str]
    canonical_name: Optional[str]
    organism_role: Optional[str]
    gram_category: Optional[str]
    synonyms: list[str]
    notes: str
    created_at: datetime


# ════════════════════════════════════════════════════════════════════════════
# STUDIES
# ════════════════════════════════════════════════════════════════════════════

class StudyCreate(BaseModel):
    project_id: int
    paper_id: Optional[int] = None
    title: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    publication_year: Optional[int] = None
    journal: Optional[str] = None
    doi_original: Optional[str] = None
    doi_normalized: Optional[str] = None
    country: Optional[str] = None
    study_type: Optional[str] = None
    abstract: Optional[str] = None
    notes: Optional[str] = ""
    review_status: str = "extracted"


class StudyUpdate(BaseModel):
    title: Optional[str] = None
    authors: Optional[list[str]] = None
    publication_year: Optional[int] = None
    journal: Optional[str] = None
    doi_original: Optional[str] = None
    doi_normalized: Optional[str] = None
    country: Optional[str] = None
    study_type: Optional[str] = None
    abstract: Optional[str] = None
    notes: Optional[str] = None
    review_status: Optional[str] = None


class StudyBrief(BaseModel):
    model_config = _ORM

    id: int
    title: Optional[str]
    publication_year: Optional[int]
    journal: Optional[str]
    doi_normalized: Optional[str]
    review_status: str
    version: int
    created_at: datetime


class StudyOut(BaseModel):
    model_config = _ORM

    id: int
    project_id: int
    paper_id: Optional[int]
    title: Optional[str]
    authors: list[str]
    publication_year: Optional[int]
    journal: Optional[str]
    doi_original: Optional[str]
    doi_normalized: Optional[str]
    country: Optional[str]
    study_type: Optional[str]
    abstract: Optional[str]
    notes: str
    review_status: str
    version: int
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int]
    updated_by: Optional[int]


# ════════════════════════════════════════════════════════════════════════════
# EXPERIMENTS
# ════════════════════════════════════════════════════════════════════════════

class ExperimentCreate(BaseModel):
    study_id: int
    experiment_label: Optional[str] = None
    food_category: Optional[str] = None
    product_name_original: Optional[str] = None
    product_name_normalized: Optional[str] = None
    product_family: Optional[str] = None
    matrix_description: Optional[str] = None
    milk_species: Optional[str] = None
    milk_treatment: Optional[str] = None
    fat_content_class: Optional[str] = None
    sampling_location: Optional[str] = None
    storage_temperature_value: Optional[float] = None
    storage_temperature_unit_original: Optional[str] = None
    storage_temperature_c: Optional[float] = None
    storage_relative_humidity: Optional[float] = None
    packaging_type: Optional[str] = None
    atmosphere_type: Optional[str] = None
    gas_composition: dict[str, float] = Field(default_factory=dict)
    light_condition: Optional[str] = None
    storage_duration_value: Optional[float] = None
    storage_duration_unit_original: Optional[str] = None
    storage_duration_days: Optional[float] = None
    study_design: Optional[str] = None
    replicate_design: Optional[str] = None
    artificial_inoculation: Optional[bool] = None
    initial_ph: Optional[float] = None
    initial_water_activity: Optional[float] = None
    initial_salt_pct: Optional[float] = None
    initial_moisture_pct: Optional[float] = None
    extra_conditions: dict[str, Any] = Field(default_factory=dict)
    review_status: str = "extracted"


class ExperimentUpdate(BaseModel):
    experiment_label: Optional[str] = None
    food_category: Optional[str] = None
    product_name_original: Optional[str] = None
    product_name_normalized: Optional[str] = None
    product_family: Optional[str] = None
    matrix_description: Optional[str] = None
    milk_species: Optional[str] = None
    milk_treatment: Optional[str] = None
    fat_content_class: Optional[str] = None
    sampling_location: Optional[str] = None
    storage_temperature_value: Optional[float] = None
    storage_temperature_unit_original: Optional[str] = None
    storage_temperature_c: Optional[float] = None
    storage_relative_humidity: Optional[float] = None
    packaging_type: Optional[str] = None
    atmosphere_type: Optional[str] = None
    gas_composition: Optional[dict[str, float]] = None
    light_condition: Optional[str] = None
    storage_duration_value: Optional[float] = None
    storage_duration_unit_original: Optional[str] = None
    storage_duration_days: Optional[float] = None
    study_design: Optional[str] = None
    replicate_design: Optional[str] = None
    artificial_inoculation: Optional[bool] = None
    initial_ph: Optional[float] = None
    initial_water_activity: Optional[float] = None
    initial_salt_pct: Optional[float] = None
    initial_moisture_pct: Optional[float] = None
    extra_conditions: Optional[dict[str, Any]] = None
    review_status: Optional[str] = None


class ExperimentBrief(BaseModel):
    model_config = _ORM

    id: int
    study_id: int
    experiment_label: Optional[str]
    product_name_normalized: Optional[str]
    food_category: Optional[str]
    storage_temperature_c: Optional[float]
    review_status: str
    created_at: datetime


class ExperimentOut(BaseModel):
    model_config = _ORM

    id: int
    study_id: int
    experiment_label: Optional[str]
    food_category: Optional[str]
    product_name_original: Optional[str]
    product_name_normalized: Optional[str]
    product_family: Optional[str]
    matrix_description: Optional[str]
    milk_species: Optional[str]
    milk_treatment: Optional[str]
    fat_content_class: Optional[str]
    sampling_location: Optional[str]
    storage_temperature_value: Optional[float]
    storage_temperature_unit_original: Optional[str]
    storage_temperature_c: Optional[float]
    storage_relative_humidity: Optional[float]
    packaging_type: Optional[str]
    atmosphere_type: Optional[str]
    gas_composition: dict[str, float]
    light_condition: Optional[str]
    storage_duration_value: Optional[float]
    storage_duration_unit_original: Optional[str]
    storage_duration_days: Optional[float]
    study_design: Optional[str]
    replicate_design: Optional[str]
    artificial_inoculation: Optional[bool]
    initial_ph: Optional[float]
    initial_water_activity: Optional[float]
    initial_salt_pct: Optional[float]
    initial_moisture_pct: Optional[float]
    extra_conditions: dict[str, Any]
    condition_signature: Optional[str]
    review_status: str
    version: int
    created_at: datetime
    updated_at: datetime


# ════════════════════════════════════════════════════════════════════════════
# TREATMENT ARMS
# ════════════════════════════════════════════════════════════════════════════

class TreatmentArmCreate(BaseModel):
    experiment_id: int
    arm_label: Optional[str] = None
    is_control: bool = False
    control_arm_id: Optional[int] = None
    treatment_type: Optional[str] = None
    ingredient_name_original: Optional[str] = None
    ingredient_name_normalized: Optional[str] = None
    ingredient_source: Optional[str] = None
    ingredient_family: Optional[str] = None
    concentration_value_original: Optional[float] = None
    concentration_unit_original: Optional[str] = None
    concentration_value_normalized: Optional[float] = None
    concentration_unit_normalized: Optional[str] = None
    application_method: Optional[str] = None
    treatment_timing: Optional[str] = None
    combination_treatments: list[dict[str, Any]] = Field(default_factory=list)
    extra_treatment: dict[str, Any] = Field(default_factory=dict)
    review_status: str = "extracted"


class TreatmentArmUpdate(BaseModel):
    arm_label: Optional[str] = None
    is_control: Optional[bool] = None
    control_arm_id: Optional[int] = None
    treatment_type: Optional[str] = None
    ingredient_name_original: Optional[str] = None
    ingredient_name_normalized: Optional[str] = None
    ingredient_source: Optional[str] = None
    ingredient_family: Optional[str] = None
    concentration_value_original: Optional[float] = None
    concentration_unit_original: Optional[str] = None
    concentration_value_normalized: Optional[float] = None
    concentration_unit_normalized: Optional[str] = None
    application_method: Optional[str] = None
    treatment_timing: Optional[str] = None
    combination_treatments: Optional[list[dict[str, Any]]] = None
    extra_treatment: Optional[dict[str, Any]] = None
    review_status: Optional[str] = None


class TreatmentArmBrief(BaseModel):
    model_config = _ORM

    id: int
    experiment_id: int
    arm_label: Optional[str]
    is_control: bool
    treatment_type: Optional[str]
    ingredient_name_normalized: Optional[str]
    concentration_value_normalized: Optional[float]
    concentration_unit_normalized: Optional[str]
    review_status: str


class TreatmentArmOut(BaseModel):
    model_config = _ORM

    id: int
    experiment_id: int
    arm_label: Optional[str]
    is_control: bool
    control_arm_id: Optional[int]
    treatment_type: Optional[str]
    ingredient_name_original: Optional[str]
    ingredient_name_normalized: Optional[str]
    ingredient_source: Optional[str]
    ingredient_family: Optional[str]
    concentration_value_original: Optional[float]
    concentration_unit_original: Optional[str]
    concentration_value_normalized: Optional[float]
    concentration_unit_normalized: Optional[str]
    application_method: Optional[str]
    treatment_timing: Optional[str]
    combination_treatments: list[dict[str, Any]]
    extra_treatment: dict[str, Any]
    review_status: str
    version: int
    created_at: datetime
    updated_at: datetime


# ════════════════════════════════════════════════════════════════════════════
# OBSERVATIONS
# ════════════════════════════════════════════════════════════════════════════

class ObservationCreate(BaseModel):
    treatment_arm_id: int
    microorganism_id: Optional[int] = None
    measurement_type: str
    measurement_subtype: Optional[str] = None
    measurement_unit_normalized: Optional[str] = None
    time_value_original: Optional[float] = None
    time_unit_original: Optional[str] = None
    time_days: Optional[float] = None
    value_original_text: Optional[str] = None
    numeric_value_original: Optional[float] = None
    unit_original: Optional[str] = None
    numeric_value_normalized: Optional[float] = None
    unit_normalized: Optional[str] = None
    mean_value: Optional[float] = None
    standard_deviation: Optional[float] = None
    standard_error: Optional[float] = None
    minimum_value: Optional[float] = None
    maximum_value: Optional[float] = None
    replicate_count: Optional[int] = None
    detection_limit: Optional[float] = None
    detection_limit_unit: Optional[str] = None
    censoring_type: str = "none"
    value_origin: str = "reported_table"
    missing_reason: Optional[str] = None
    is_imputed: bool = False
    is_derived: bool = False
    significance_letter: Optional[str] = None
    review_status: str = "extracted"


class ObservationUpdate(BaseModel):
    microorganism_id: Optional[int] = None
    measurement_type: Optional[str] = None
    measurement_subtype: Optional[str] = None
    measurement_unit_normalized: Optional[str] = None
    time_value_original: Optional[float] = None
    time_unit_original: Optional[str] = None
    time_days: Optional[float] = None
    value_original_text: Optional[str] = None
    numeric_value_original: Optional[float] = None
    unit_original: Optional[str] = None
    numeric_value_normalized: Optional[float] = None
    unit_normalized: Optional[str] = None
    mean_value: Optional[float] = None
    standard_deviation: Optional[float] = None
    standard_error: Optional[float] = None
    minimum_value: Optional[float] = None
    maximum_value: Optional[float] = None
    replicate_count: Optional[int] = None
    detection_limit: Optional[float] = None
    detection_limit_unit: Optional[str] = None
    censoring_type: Optional[str] = None
    value_origin: Optional[str] = None
    missing_reason: Optional[str] = None
    significance_letter: Optional[str] = None
    review_status: Optional[str] = None
    reviewer_note: Optional[str] = None


class ObservationOut(BaseModel):
    model_config = _ORM

    id: int
    treatment_arm_id: int
    microorganism_id: Optional[int]
    measurement_type: str
    measurement_subtype: Optional[str]
    measurement_unit_normalized: Optional[str]
    time_value_original: Optional[float]
    time_unit_original: Optional[str]
    time_days: Optional[float]
    value_original_text: Optional[str]
    numeric_value_original: Optional[float]
    unit_original: Optional[str]
    numeric_value_normalized: Optional[float]
    unit_normalized: Optional[str]
    mean_value: Optional[float]
    standard_deviation: Optional[float]
    standard_error: Optional[float]
    minimum_value: Optional[float]
    maximum_value: Optional[float]
    replicate_count: Optional[int]
    detection_limit: Optional[float]
    detection_limit_unit: Optional[str]
    censoring_type: str
    value_origin: str
    missing_reason: Optional[str]
    is_imputed: bool
    is_derived: bool
    significance_letter: Optional[str]
    quality_score: Optional[float]
    review_status: str
    version: int
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int]
    updated_by: Optional[int]
    extraction_run_id: Optional[int]


class ObservationBulkCreate(BaseModel):
    observations: list[ObservationCreate]


# ════════════════════════════════════════════════════════════════════════════
# PROVENANCE
# ════════════════════════════════════════════════════════════════════════════

class ProvenanceRecordOut(BaseModel):
    model_config = _ORM

    id: int
    entity_type: str
    entity_id: int
    field_name: Optional[str]
    paper_id: int
    page_number: Optional[int]
    section_name: Optional[str]
    table_number: Optional[int]
    figure_number: Optional[int]
    source_snippet: Optional[str]
    confidence: Optional[float]
    manually_verified: bool
    created_at: datetime


# ════════════════════════════════════════════════════════════════════════════
# VALIDATION ISSUES
# ════════════════════════════════════════════════════════════════════════════

class ValidationIssueOut(BaseModel):
    model_config = _ORM

    id: int
    entity_type: str
    entity_id: int
    field_name: Optional[str]
    rule_code: str
    severity: str
    message: str
    detected_value: Optional[str]
    expected_condition: Optional[str]
    remediation_hint: Optional[str]
    resolved: bool
    resolution_note: Optional[str]
    resolved_by: Optional[int]
    resolved_at: Optional[datetime]
    created_at: datetime


class ValidationIssueResolve(BaseModel):
    resolution_note: str


# ════════════════════════════════════════════════════════════════════════════
# AUDIT EVENTS
# ════════════════════════════════════════════════════════════════════════════

class AuditEventOut(BaseModel):
    model_config = _ORM

    id: int
    actor_id: Optional[int]
    entity_type: str
    entity_id: int
    action: str
    diff: Optional[dict[str, Any]] = None
    reason: Optional[str]
    source: Optional[str]
    project_id: Optional[int]
    created_at: datetime


# ════════════════════════════════════════════════════════════════════════════
# PROJECT MEMBERS
# ════════════════════════════════════════════════════════════════════════════

class ProjectMemberCreate(BaseModel):
    user_email: str
    role: str = "reviewer"


class ProjectMemberUpdate(BaseModel):
    role: str


class ProjectMemberOut(BaseModel):
    model_config = _ORM

    id: int
    project_id: int
    user_id: int
    role: str
    joined_at: datetime
    user: Optional[UserBrief] = None


# ════════════════════════════════════════════════════════════════════════════
# COMMENTS
# ════════════════════════════════════════════════════════════════════════════

class CommentCreate(BaseModel):
    entity_type: str
    entity_id: int
    parent_id: Optional[int] = None
    body: str


class CommentUpdate(BaseModel):
    body: str


class CommentOut(BaseModel):
    model_config = _ORM

    id: int
    entity_type: str
    entity_id: int
    parent_id: Optional[int]
    author_id: int
    body: str
    resolved: bool
    created_at: datetime
    updated_at: datetime
    author: Optional[UserBrief] = None


# ════════════════════════════════════════════════════════════════════════════
# NORMALIZATION MAPPINGS
# ════════════════════════════════════════════════════════════════════════════

class NormalizationMappingCreate(BaseModel):
    project_id: Optional[int] = None
    mapping_type: str
    original_term: str
    canonical_term: str
    canonical_id: Optional[int] = None
    confidence: float = 1.0
    source: str = "manual"


class NormalizationMappingOut(BaseModel):
    model_config = _ORM

    id: int
    project_id: Optional[int]
    mapping_type: str
    original_term: str
    canonical_term: str
    canonical_id: Optional[int]
    confidence: float
    source: str
    created_at: datetime
    applied_count: int


# ════════════════════════════════════════════════════════════════════════════
# TRAJECTORIES
# ════════════════════════════════════════════════════════════════════════════

class TrajectoryCreate(BaseModel):
    project_id: int
    experiment_id: Optional[int] = None
    treatment_arm_id: Optional[int] = None
    label: Optional[str] = None
    measurement_type: str
    measurement_subtype: Optional[str] = None
    microorganism_id: Optional[int] = None
    observation_ids: list[int] = Field(default_factory=list)
    notes: Optional[str] = None


class TrajectoryOut(BaseModel):
    model_config = _ORM

    id: int
    project_id: int
    experiment_id: Optional[int]
    treatment_arm_id: Optional[int]
    label: Optional[str]
    measurement_type: str
    measurement_subtype: Optional[str]
    microorganism_id: Optional[int]
    process_class: Optional[str]
    n_points: int
    time_min_days: Optional[float]
    time_max_days: Optional[float]
    has_control: bool
    data_sufficient: bool
    notes: Optional[str]
    observation_ids: list[int]
    created_at: datetime
    updated_at: datetime


# ════════════════════════════════════════════════════════════════════════════
# MODEL FITS AND RUNS
# ════════════════════════════════════════════════════════════════════════════

class ModelRunCreate(BaseModel):
    trajectory_id: int
    project_id: int


class ModelFitOut(BaseModel):
    model_config = _ORM

    id: int
    run_id: int
    model_name: str
    process_class: Optional[str]
    converged: bool
    convergence_message: Optional[str]
    parameters: dict[str, Any]
    parameter_se: dict[str, Any]
    mae: Optional[float]
    rmse: Optional[float]
    r_squared: Optional[float]
    adjusted_r_squared: Optional[float]
    aic: Optional[float]
    bic: Optional[float]
    loo_mae: Optional[float]
    loo_rmse: Optional[float]
    biological_violations: int
    applicability_status: Optional[str]
    applicability_reasons: list[str]
    rank: Optional[int]
    equation_text: Optional[str]
    created_at: datetime


class ModelRunOut(BaseModel):
    model_config = _ORM

    id: int
    trajectory_id: int
    project_id: int
    status: str
    models_tried: int
    models_converged: int
    selected_model_id: Optional[int]
    error_message: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
    fits: list[ModelFitOut] = Field(default_factory=list)


# ════════════════════════════════════════════════════════════════════════════
# IMPUTATION PROPOSALS
# ════════════════════════════════════════════════════════════════════════════

class ImputationProposalOut(BaseModel):
    model_config = _ORM

    id: int
    project_id: int
    trajectory_id: Optional[int]
    fit_id: Optional[int]
    target_observation_id: Optional[int]
    target_arm_id: Optional[int]
    target_time_days: Optional[float]
    target_measurement_type: Optional[str]
    predicted_value: Optional[float]
    lower_bound: Optional[float]
    upper_bound: Optional[float]
    interval_type: Optional[str]
    is_interpolation: bool
    extrapolation_days: float
    applicability_status: Optional[str]
    applicability_reasons: list[str]
    cross_validation_mae: Optional[float]
    cross_validation_rmse: Optional[float]
    n_points_used: Optional[int]
    model_name: Optional[str]
    reviewer_decision: Optional[str]
    reviewer_note: Optional[str]
    reviewed_at: Optional[datetime]
    created_at: datetime


class ImputationReview(BaseModel):
    decision: str   # accepted|rejected
    note: Optional[str] = None


# ════════════════════════════════════════════════════════════════════════════
# THRESHOLDS
# ════════════════════════════════════════════════════════════════════════════

class ThresholdCreate(BaseModel):
    project_id: int
    name: str
    measurement_type: str
    threshold_value: float
    threshold_unit: Optional[str] = None
    comparison_operator: str = "<="
    product_scope: Optional[str] = None
    microorganism_scope: Optional[str] = None
    source_type: str = "team_defined"
    source_citation: Optional[str] = None
    notes: Optional[str] = None


class ThresholdUpdate(BaseModel):
    name: Optional[str] = None
    measurement_type: Optional[str] = None
    threshold_value: Optional[float] = None
    threshold_unit: Optional[str] = None
    comparison_operator: Optional[str] = None
    product_scope: Optional[str] = None
    microorganism_scope: Optional[str] = None
    source_type: Optional[str] = None
    source_citation: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class ThresholdOut(BaseModel):
    model_config = _ORM

    id: int
    project_id: int
    name: str
    measurement_type: str
    threshold_value: float
    threshold_unit: Optional[str]
    comparison_operator: str
    product_scope: Optional[str]
    microorganism_scope: Optional[str]
    source_type: str
    source_citation: Optional[str]
    notes: Optional[str]
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime


# ════════════════════════════════════════════════════════════════════════════
# DATASET SNAPSHOTS
# ════════════════════════════════════════════════════════════════════════════

class SnapshotCreate(BaseModel):
    project_id: int
    label: str
    description: Optional[str] = None
    filters: dict[str, Any] = Field(default_factory=dict)
    includes_imputed: bool = False
    only_approved: bool = True
    feature_config: dict[str, Any] = Field(default_factory=dict)


class SnapshotOut(BaseModel):
    model_config = _ORM

    id: int
    project_id: int
    label: str
    description: Optional[str]
    filters: dict[str, Any]
    row_count: int
    observation_count: int
    includes_imputed: bool
    only_approved: bool
    feature_config: dict[str, Any]
    snapshot_hash: Optional[str]
    created_by: Optional[int]
    created_at: datetime


# ════════════════════════════════════════════════════════════════════════════
# EXPORT RUNS
# ════════════════════════════════════════════════════════════════════════════

class ExportRequest(BaseModel):
    project_id: int
    format: str = "excel"   # excel|csv_zip|json|parquet
    snapshot_id: Optional[int] = None
    filters: dict[str, Any] = Field(default_factory=dict)


class ExportRunOut(BaseModel):
    model_config = _ORM

    id: int
    project_id: int
    snapshot_id: Optional[int]
    format: str
    status: str
    file_size_bytes: Optional[int]
    created_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]


# ════════════════════════════════════════════════════════════════════════════
# EXPERIMENT MICROORGANISM
# ════════════════════════════════════════════════════════════════════════════

class ExperimentMicroorganismCreate(BaseModel):
    experiment_id: int
    microorganism_id: int
    role_in_study: Optional[str] = None
    inoculum_level: Optional[float] = None
    inoculum_unit: Optional[str] = None


class ExperimentMicroorganismOut(BaseModel):
    model_config = _ORM

    id: int
    experiment_id: int
    microorganism_id: int
    role_in_study: Optional[str]
    inoculum_level: Optional[float]
    inoculum_unit: Optional[str]
    microorganism: Optional[MicroorganismOut] = None


# ════════════════════════════════════════════════════════════════════════════
# AGGREGATED VIEWS (used by frontend pages that need joined data)
# ════════════════════════════════════════════════════════════════════════════

class StudyDetail(StudyOut):
    """Study with nested experiments summary."""
    experiments: list[ExperimentBrief] = Field(default_factory=list)
    paper_original_name: Optional[str] = None
    open_issues: int = 0


class ExperimentDetail(ExperimentOut):
    """Experiment with nested treatment arms and microorganisms."""
    treatment_arms: list[TreatmentArmBrief] = Field(default_factory=list)
    microorganisms: list[ExperimentMicroorganismOut] = Field(default_factory=list)
    study_title: Optional[str] = None
    observation_count: int = 0


class ProjectStats(BaseModel):
    """Summary statistics for a project overview page."""
    study_count: int = 0
    experiment_count: int = 0
    observation_count: int = 0
    paper_count: int = 0
    approved_count: int = 0
    needs_review_count: int = 0
    open_issues: int = 0
    member_count: int = 0
    last_extraction_at: Optional[datetime] = None
