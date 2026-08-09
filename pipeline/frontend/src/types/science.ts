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
  /** What the paper calls it, e.g. "Total viable count". This is the label to display. */
  indicator_name: string
  /** The category it belongs to: "microbial" or "chemical". Not a display name. */
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
  /** Null when the paper names the additive without stating how much was used. */
  concentration: number | null
  concentration_unit: string | null
}

/** One value at one (day, indicator) for one experiment. */
export interface Measurement {
  day: number
  indicator_id: number
  indicator_name: string
  indicator_type: string
  indicator_unit: string
  indicator_threshold: number | null
  indicator_value: number
  /**
   * How many separately-printed readings were averaged into this value; 1 when the paper
   * printed a single value or its own mean. Replaces `value_is_approximate`, which
   * recorded a provenance fact the evidence rows already carry.
   */
  replicates: number
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
  field_name: string
  page_number: number | null
  /** "prose" | "table" | "figure" */
  source_type: string
  source_label: string | null
  exact_text: string | null
  /**
   * How the value was arrived at: "stated", "derived" or "inferred". The last two carry a
   * `rationale`, so a computed value is never read as one the paper stated outright.
   */
  method: string
  rationale: string | null
  bounding_box: BoundingBox | null
  /** Scored by the pipeline against the source text, never supplied by the model. */
  confidence: number | null
  figure_series: string | null
  x_axis_value: number | null
  y_axis_value: number | null
  value_is_approximate: boolean
  is_chart_derived: boolean
}

export interface ExperimentSummary {
  id: number
  paper_id: number
  meat_matrix: string
  /**
   * Null when the paper never describes this arm's handling. Whether it addressed it at
   * all is answered by an evidence span for `field_name === "treatment"`, not by this.
   */
  treatment: string | null
  /** Mass in grams of one experimental sample unit. */
  weight_g: number | null
  ingredients: ExperimentIngredient[]
  measurement_count: number
  created_at: string | null
}

export interface ExperimentDetail {
  id: number
  paper_id: number
  meat_matrix: string
  treatment: string | null
  weight_g: number | null
  created_at: string | null
  ingredients: ExperimentIngredient[]
  measurements: Measurement[]
  evidence: Evidence[]
}
