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
  paper_count: number
  row_count: number
}

export interface Paper {
  id: number
  project_id: number
  filename: string
  original_name: string
  page_count: number
  status: 'uploaded' | 'extracting' | 'extracted' | 'reviewed' | 'error'
  error_message: string
  uploaded_at: string
  row_count: number
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
