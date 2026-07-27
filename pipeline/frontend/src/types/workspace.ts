/** Types mirroring `extraction/app/schemas/workspace.py`. */

/**
 * Pre-signed, expiring URLs for an asset's binaries.
 *
 * The client no longer constructs these. It cannot sign them, and constructing them
 * client-side is exactly what forced the gateway to accept unauthenticated `/image` and
 * `/csv` requests. `null` means the asset has no such file.
 */
export interface AssetLinks {
  image: string | null
  page_image: string | null
  csv: string | null
}

export type AssetClassification =
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

export type ConversionStatus =
  | 'pending'
  | 'processing'
  | 'complete'
  | 'failed'
  | 'skipped'
  | 'not_a_chart'
  | 'not_applicable'
  | null

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
  classification: AssetClassification
  conversion_status: ConversionStatus
  conversion_error: string | null
  relevance_score: number
  selected_for_llm: boolean
  user_note: string | null
  links: AssetLinks
  created_at: string | null
}

export interface ContextLink {
  id: number
  link_type: string
  text: string
  item_ref: string | null
  page_number: number | null
  score: number
}

export interface AssetDetail extends ExtractionAsset {
  context_links: ContextLink[]
}

export interface AssetPage {
  total: number
  items: ExtractionAsset[]
}

/** Every "start work" endpoint returns exactly this. Progress comes from the job stream. */
export interface JobAccepted {
  job_id: number
  status: string
}

export interface EvidenceAsset extends AssetDetail {
  link_count: number
  auto_include: boolean
  auto_reason: string | null
  is_decorative: boolean
  effective_include: boolean
  exclude_reason: string | null
}

export interface EvidenceParagraph {
  asset_id: number
  link_id: number
  link_type: string
  text: string
  page_number: number | null
  score: number
  section_name: string | null
  asset_caption: string | null
  relevance_score: number
  auto_reason: string | null
}

export interface EvidencePackages {
  paragraphs: EvidenceParagraph[]
  native_tables: EvidenceAsset[]
  chart_csvs: EvidenceAsset[]
  excluded: EvidenceAsset[]
  totals: {
    paragraphs: number
    native_tables: number
    chart_csvs: number
    excluded: number
  }
  chart_conversion_available: boolean
  chart_conversion_error: string | null
}
