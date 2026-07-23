// ─── Legacy types (preserved) ──────────────────────────────────────────────

export interface User {
  id: number
  email: string
  full_name: string
  is_active: boolean
}

export interface SchemaField {
  name: string
  label: string
  type: 'text' | 'number' | 'select' | 'boolean'
  unit?: string
  options?: string[]
  required?: boolean
  validation?: { min?: number; max?: number }
}

export interface Project {
  id: number
  name: string
  description: string
  schema_fields: SchemaField[]
  created_at: string
  updated_at: string
  owner_id: number
  paper_count?: number
  row_count?: number
}

export interface Paper {
  id: number
  project_id: number
  filename: string
  original_name: string
  file_hash?: string
  page_count: number
  status: 'uploaded' | 'extracting' | 'extracted' | 'reviewed' | 'error'
  error_message: string
  uploaded_at: string
  row_count?: number
}

export interface ProvenanceInfo {
  page?: number
  table?: string
  confidence?: number
}

export interface ExtractedRow {
  id: number
  paper_id: number
  project_id: number
  data: Record<string, unknown>
  provenance: Record<string, ProvenanceInfo>
  status: 'pending' | 'approved' | 'rejected' | 'edited'
  reviewer_note: string
  created_at: string
  updated_at: string
}

export interface Analytics {
  summary: {
    total_papers: number
    total_rows: number
    approved: number
    pending: number
    rejected: number
  }
  paper_status: Record<string, number>
  papers: Array<{ paper_id: number; name: string; status: string; page_count: number; row_count: number }>
  field_coverage: Record<string, { label: string; filled: number; total: number; pct: number }>
  distributions: Record<string, { label: string; count: number; min: number; max: number; mean: number; values: number[] }>
  categoricals: Record<string, { label: string; data: Array<{ value: string; count: number }> }>
}

// ─── Canonical scientific types ────────────────────────────────────────────

export type ReviewStatus =
  | 'extracted' | 'needs_review' | 'in_review'
  | 'changes_requested' | 'approved' | 'rejected' | 'superseded'

export type ValueOrigin =
  | 'reported_table' | 'reported_text' | 'reported_figure'
  | 'graph_estimated' | 'calculated' | 'unit_converted'
  | 'normalized' | 'model_imputed' | 'manual_entry'
  | 'imported_external' | 'synthetic'

export type MissingReason =
  | 'not_reported' | 'not_measured' | 'not_applicable'
  | 'below_detection_limit' | 'above_detection_limit'
  | 'unreadable_source' | 'extraction_failed'
  | 'removed_after_validation' | 'figure_only_not_digitized'
  | 'intentionally_masked_for_validation' | 'unknown'

export type ApplicabilityStatus = 'green' | 'yellow' | 'red'

// ── Microorganism ──────────────────────────────────────────────────────────

export interface Microorganism {
  id: number
  project_id: number | null
  genus: string
  species?: string
  strain?: string
  original_text?: string
  canonical_name?: string
  organism_role?: string
  gram_category?: string
  synonyms: string[]
  notes: string
  created_at: string
}

// ── Study ─────────────────────────────────────────────────────────────────

export interface StudyBrief {
  id: number
  title?: string
  publication_year?: number
  journal?: string
  doi_normalized?: string
  review_status: ReviewStatus
  version: number
  created_at: string
}

export interface Study {
  id: number
  project_id: number
  paper_id?: number
  title?: string
  authors: string[]
  publication_year?: number
  journal?: string
  doi_original?: string
  doi_normalized?: string
  country?: string
  study_type?: string
  abstract?: string
  notes: string
  review_status: ReviewStatus
  version: number
  created_at: string
  updated_at: string
  created_by?: number
  updated_by?: number
  // Expanded
  experiments?: ExperimentBrief[]
  paper_original_name?: string
  open_issues?: number
}

// ── Experiment ────────────────────────────────────────────────────────────

export interface ExperimentBrief {
  id: number
  study_id: number
  experiment_label?: string
  product_name_normalized?: string
  food_category?: string
  storage_temperature_c?: number
  review_status: ReviewStatus
  created_at: string
}

export interface Experiment {
  id: number
  study_id: number
  experiment_label?: string
  food_category?: string
  product_name_original?: string
  product_name_normalized?: string
  product_family?: string
  matrix_description?: string
  milk_species?: string
  milk_treatment?: string
  fat_content_class?: string
  sampling_location?: string
  storage_temperature_value?: number
  storage_temperature_unit_original?: string
  storage_temperature_c?: number
  storage_relative_humidity?: number
  packaging_type?: string
  atmosphere_type?: string
  gas_composition: Record<string, number>
  light_condition?: string
  storage_duration_value?: number
  storage_duration_unit_original?: string
  storage_duration_days?: number
  study_design?: string
  replicate_design?: string
  artificial_inoculation?: boolean
  initial_ph?: number
  initial_water_activity?: number
  initial_salt_pct?: number
  initial_moisture_pct?: number
  extra_conditions: Record<string, unknown>
  condition_signature?: string
  review_status: ReviewStatus
  version: number
  created_at: string
  updated_at: string
  // Expanded
  treatment_arms?: TreatmentArmBrief[]
  microorganisms?: ExperimentMicroorganism[]
  study_title?: string
  observation_count?: number
}

// ── Treatment Arm ─────────────────────────────────────────────────────────

export interface TreatmentArmBrief {
  id: number
  experiment_id: number
  arm_label?: string
  is_control: boolean
  treatment_type?: string
  ingredient_name_normalized?: string
  concentration_value_normalized?: number
  concentration_unit_normalized?: string
  review_status: ReviewStatus
}

export interface TreatmentArm {
  id: number
  experiment_id: number
  arm_label?: string
  is_control: boolean
  control_arm_id?: number
  treatment_type?: string
  ingredient_name_original?: string
  ingredient_name_normalized?: string
  ingredient_source?: string
  ingredient_family?: string
  concentration_value_original?: number
  concentration_unit_original?: string
  concentration_value_normalized?: number
  concentration_unit_normalized?: string
  application_method?: string
  treatment_timing?: string
  combination_treatments: Record<string, unknown>[]
  extra_treatment: Record<string, unknown>
  review_status: ReviewStatus
  version: number
  created_at: string
  updated_at: string
}

// ── Observation ───────────────────────────────────────────────────────────

export interface Observation {
  id: number
  treatment_arm_id: number
  microorganism_id?: number
  measurement_type: string
  measurement_subtype?: string
  measurement_unit_normalized?: string
  time_value_original?: number
  time_unit_original?: string
  time_days?: number
  value_original_text?: string
  numeric_value_original?: number
  unit_original?: string
  numeric_value_normalized?: number
  unit_normalized?: string
  mean_value?: number
  standard_deviation?: number
  standard_error?: number
  minimum_value?: number
  maximum_value?: number
  replicate_count?: number
  detection_limit?: number
  detection_limit_unit?: string
  censoring_type: string
  value_origin: ValueOrigin
  missing_reason?: MissingReason
  is_imputed: boolean
  is_derived: boolean
  significance_letter?: string
  quality_score?: number
  review_status: ReviewStatus
  version: number
  created_at: string
  updated_at: string
  created_by?: number
  updated_by?: number
  extraction_run_id?: number
}

// ── ExperimentMicroorganism ───────────────────────────────────────────────

export interface ExperimentMicroorganism {
  id: number
  experiment_id: number
  microorganism_id: number
  role_in_study?: string
  inoculum_level?: number
  inoculum_unit?: string
  microorganism?: Microorganism
}

// ── Job ───────────────────────────────────────────────────────────────────

export type JobStatus =
  | 'queued' | 'parsing' | 'chunking'
  | 'extracting_metadata' | 'extracting_tables' | 'extracting_observations'
  | 'normalizing' | 'validating' | 'awaiting_review'
  | 'completed' | 'partial_success' | 'failed' | 'cancelled'

export interface Job {
  id: number
  project_id?: number
  paper_id?: number
  job_type: string
  status: JobStatus
  progress: number
  current_step: string
  total_steps: number
  error_message: string
  result: Record<string, unknown>
  celery_task_id?: string
  created_at: string
  started_at?: string
  completed_at?: string
}

// ── Provenance & Validation ───────────────────────────────────────────────

export interface ProvenanceRecord {
  id: number
  entity_type: string
  entity_id: number
  field_name?: string
  paper_id: number
  page_number?: number
  section_name?: string
  table_number?: number
  source_snippet?: string
  confidence?: number
  manually_verified: boolean
  created_at: string
}

export interface ValidationIssue {
  id: number
  entity_type: string
  entity_id: number
  field_name?: string
  rule_code: string
  severity: 'error' | 'warning' | 'info'
  message: string
  detected_value?: string
  expected_condition?: string
  remediation_hint?: string
  resolved: boolean
  resolution_note?: string
  resolved_by?: number
  resolved_at?: string
  created_at: string
}

// ── Audit ─────────────────────────────────────────────────────────────────

export interface AuditEvent {
  id: number
  actor_id?: number
  entity_type: string
  entity_id: number
  action: string
  diff?: Record<string, { before: unknown; after: unknown }>
  reason?: string
  source?: string
  project_id?: number
  created_at: string
}

// ── Team ──────────────────────────────────────────────────────────────────

export interface ProjectMember {
  id: number
  project_id: number
  user_id: number
  role: 'owner' | 'admin' | 'reviewer' | 'analyst' | 'viewer'
  joined_at: string
  user?: { id: number; email: string; full_name: string }
}

export interface Comment {
  id: number
  entity_type: string
  entity_id: number
  parent_id?: number
  author_id: number
  body: string
  resolved: boolean
  created_at: string
  updated_at: string
  author?: { id: number; email: string; full_name: string }
  replies?: Comment[]
}

// ── Normalization ─────────────────────────────────────────────────────────

export interface NormalizationMapping {
  id: number
  project_id?: number
  mapping_type: string
  original_term: string
  canonical_term: string
  canonical_id?: number
  confidence: number
  source: string
  created_at: string
  applied_count: number
}

// ── Trajectories & Models ─────────────────────────────────────────────────

export interface Trajectory {
  id: number
  project_id: number
  experiment_id?: number
  treatment_arm_id?: number
  label?: string
  measurement_type: string
  measurement_subtype?: string
  microorganism_id?: number
  process_class?: string
  n_points: number
  time_min_days?: number
  time_max_days?: number
  has_control: boolean
  data_sufficient: boolean
  notes?: string
  observation_ids: number[]
  created_at: string
  updated_at: string
}

export interface ModelFit {
  id: number
  run_id: number
  model_name: string
  process_class?: string
  converged: boolean
  convergence_message?: string
  parameters: Record<string, number>
  parameter_se: Record<string, number>
  mae?: number
  rmse?: number
  r_squared?: number
  adjusted_r_squared?: number
  aic?: number
  bic?: number
  loo_mae?: number
  loo_rmse?: number
  biological_violations: number
  applicability_status?: ApplicabilityStatus
  applicability_reasons: string[]
  rank?: number
  equation_text?: string
  created_at: string
}

export interface ModelRun {
  id: number
  trajectory_id: number
  project_id: number
  status: string
  models_tried: number
  models_converged: number
  selected_model_id?: number
  error_message?: string
  created_at: string
  completed_at?: string
  fits: ModelFit[]
}

// ── Imputations ───────────────────────────────────────────────────────────

export interface ImputationProposal {
  id: number
  project_id: number
  trajectory_id?: number
  fit_id?: number
  target_observation_id?: number
  target_arm_id?: number
  target_time_days?: number
  target_measurement_type?: string
  predicted_value?: number
  lower_bound?: number
  upper_bound?: number
  interval_type?: string
  is_interpolation: boolean
  extrapolation_days: number
  applicability_status?: ApplicabilityStatus
  applicability_reasons: string[]
  cross_validation_mae?: number
  cross_validation_rmse?: number
  n_points_used?: number
  model_name?: string
  reviewer_decision?: 'pending' | 'accepted' | 'rejected' | 'superseded'
  reviewer_note?: string
  reviewed_at?: string
  created_at: string
}

// ── Thresholds ────────────────────────────────────────────────────────────

export interface Threshold {
  id: number
  project_id: number
  name: string
  measurement_type: string
  threshold_value: number
  threshold_unit?: string
  comparison_operator: string
  product_scope?: string
  microorganism_scope?: string
  source_type: string
  source_citation?: string
  notes?: string
  is_active: boolean
  version: number
  created_at: string
  updated_at: string
}

// ── Snapshots & Exports ───────────────────────────────────────────────────

export interface DatasetSnapshot {
  id: number
  project_id: number
  label: string
  description?: string
  filters: Record<string, unknown>
  row_count: number
  observation_count: number
  includes_imputed: boolean
  only_approved: boolean
  feature_config: Record<string, unknown>
  snapshot_hash?: string
  created_by?: number
  created_at: string
}

export interface ExportRun {
  id: number
  project_id: number
  snapshot_id?: number
  format: 'excel' | 'csv_zip' | 'json' | 'parquet'
  status: 'pending' | 'building' | 'completed' | 'failed'
  file_size_bytes?: number
  created_at: string
  completed_at?: string
  error_message?: string
}

// ── Project statistics ────────────────────────────────────────────────────

export interface ProjectStats {
  study_count: number
  experiment_count: number
  observation_count: number
  paper_count: number
  approved_count: number
  needs_review_count: number
  open_issues: number
  member_count: number
  last_extraction_at?: string
}

// ── Extraction runs ───────────────────────────────────────────────────────

export interface ExtractionRun {
  id: number
  paper_id: number
  job_id?: number
  provider?: string
  model_name?: string
  prompt_version?: string
  status: string
  pages_processed: number
  chunks_created: number
  rows_extracted: number
  tables_found: number
  error_message: string
  created_at: string
  completed_at?: string
}
