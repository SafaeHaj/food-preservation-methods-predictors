/**
 * Platform types — users, projects, papers, jobs, audit, team.
 *
 * The scientific types live in `types/science.ts` and mirror the extraction service's
 * response models. This file used to carry a second set of them (studies, experiments,
 * treatment arms, observations, trajectories, model fits, imputations, thresholds,
 * snapshots, exports) for a hierarchy that no longer exists, plus the flat `ExtractedRow`
 * shape from the extraction path before that. Both are gone.
 */

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
  /** The caller's role, so the UI can hide actions it would only be refused for. */
  your_role?: 'owner' | 'admin' | 'reviewer' | 'analyst' | 'viewer'
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
  /** Elements Docling found in the PDF. */
  asset_count: number
  /** Structured experiments the LLM produced from those elements. */
  experiment_count: number
}

// ── Jobs ──────────────────────────────────────────────────────────────────

export type JobStatus =
  | 'queued' | 'running' | 'completed' | 'partial_success' | 'failed' | 'cancelled'

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

// ── Project statistics ────────────────────────────────────────────────────

/** Mirrors `shared/schemas/projects.ProjectStats`: counts over the scientific schema. */
export interface ProjectStats {
  paper_count: number
  experiment_count: number
  measurement_count: number
  ingredient_count: number
  indicator_count: number
  /** Indicators carrying a threshold — what decides whether the project can be modelled. */
  indicators_with_threshold: number
  member_count: number
  last_extraction_at?: string
}
