export interface ExtractionAsset {
  id: number
  paper_id: number
  project_id: number
  paper_name?: string | null
  docling_item_ref: string | null
  asset_type: 'figure' | 'native_table'
  page_number: number | null
  bbox: { x1: number; y1: number; x2: number; y2: number } | null
  section_name: string | null
  caption: string | null
  has_image: boolean
  has_page_image: boolean
  has_csv: boolean
  csv_rows: number | null
  csv_cols: number | null
  classification:
    | 'chart'
    | 'native_table'
    | 'photograph'
    | 'diagram'
    | 'chemical_structure'
    | 'multi_panel_figure'
    | 'publisher_logo'
    | 'license_icon'
    | 'decorative_asset'
    | 'unknown'
  conversion_status:
    | 'pending'
    | 'processing'
    | 'complete'
    | 'failed'
    | 'skipped'
    | 'not_a_chart'
    | 'not_applicable'
    | null
  conversion_error: string | null
  relevance_score: number
  selected_for_llm: boolean
  user_note: string | null
  created_at: string | null
}

export interface ContextLink {
  link_type: string
  text: string
  item_ref: string | null
  page_number: number | null
  score: number
}

export interface AssetDetail extends ExtractionAsset {
  context_links: ContextLink[]
}

export interface WorkspaceStatus {
  status: 'not_started' | 'queued' | 'running' | 'completed' | 'failed'
  progress: number
  current_step: string
  asset_count: number
  job_id: number | null
  started_at: string | null
  completed_at: string | null
  error: string | null
  result: {
    figures: number
    charts: number
    native_tables: number
    texts: number
    total_assets: number
    page_count: number
    chart_conversion_available?: boolean
    skipped_charts?: number
    decorative_excluded?: number
  } | null
}
