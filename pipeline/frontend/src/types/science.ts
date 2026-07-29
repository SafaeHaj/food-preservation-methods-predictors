/**
 * The scientific schema, exactly as the extraction service serialises it
 * (see `extraction/app/schemas/science.py`).
 *
 *   experiments ─┬─ experiment_ingredients ── ingredients
 *                └─ measurements ── indicators   (+ evidence)
 *
 * These are the rows the LLM produced, read verbatim. There is no second, reshaped copy of
 * them any more: what the reviewer sees here is what every downstream consumer reads.
 */

export interface Ingredient {
  id: number
  ingredient_name: string
  functional_class: string
  /** Biological origin of the ingredient, not the paper it came from. */
  source: string
}

export interface Indicator {
  id: number
  indicator_type: string
  indicator_unit: string
  indicator_threshold: number | null
}

/** One ingredient as it is used in a specific experiment, with its concentration. */
export interface ExperimentIngredient {
  ingredient_id: number
  ingredient_name: string
  functional_class: string
  source: string
  concentration: number
  concentration_unit: string
}

/** One value at one (day, indicator) for one experiment. */
export interface Measurement {
  day: number
  indicator_id: number
  indicator_type: string
  indicator_unit: string
  indicator_threshold: number | null
  indicator_value: number
  value_is_approximate: boolean
}

export interface BoundingBox {
  x1: number
  y1: number
  x2: number
  y2: number
}

export interface Evidence {
  id: number
  entity_type: string
  entity_key: Record<string, unknown>
  field_name: string | null
  page_number: number | null
  source_type: string
  source_label: string | null
  exact_text: string | null
  bounding_box: BoundingBox | null
  confidence: number | null
  figure_series: string | null
  x_axis_value: number | null
  y_axis_value: number | null
  value_is_approximate: boolean
  is_chart_derived: boolean
  image_url: string | null
  thumbnail_url: string | null
}

export interface ExperimentSummary {
  id: number
  paper_id: number
  meat_matrix: string
  treatment: string
  ingredients: ExperimentIngredient[]
  measurement_count: number
  created_at: string | null
}

export interface ExperimentDetail {
  id: number
  paper_id: number
  meat_matrix: string
  treatment: string
  created_at: string | null
  ingredients: ExperimentIngredient[]
  measurements: Measurement[]
  evidence: Evidence[]
}
