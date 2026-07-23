export type ModelFamily = 'kinetic' | 'survival'
export type DataType = 'numeric' | 'boolean' | 'categorical' | 'text'
export type RoleId =
  // Shared
  | 'time' | 'response' | 'temperature' | 'pH' | 'aw'
  | 'preservative' | 'concentration' | 'packaging'
  | 'microorganism' | 'product_type' | 'product_category'
  | 'control_indicator' | 'study_id' | 'replicate'
  // Kinetic-specific
  | 'trajectory_id' | 'failure_threshold' | 'measurement_stage' | 'treatment'
  // Survival-specific
  | 'event' | 'additional_predictor'
  // Special
  | 'ignore' | 'unassigned'

export interface ColumnRole {
  id: RoleId
  label: string
  description: string
  unit?: string
  families: ModelFamily[]
  required: ModelFamily[]
}

export const ROLES: ColumnRole[] = [
  // ── Kinetic required ────────────────────────────────────────────────────
  {
    id: 'trajectory_id', label: 'Experiment / Trajectory ID',
    description: 'Groups rows into individual growth or inactivation curves',
    families: ['kinetic'], required: ['kinetic'],
  },
  {
    id: 'time', label: 'Time',
    description: 'Measurement time (kinetic) or time to failure/censoring (survival)',
    unit: 'h, min, or days',
    families: ['kinetic', 'survival'], required: ['kinetic', 'survival'],
  },
  {
    id: 'response', label: 'Response / Microbial count',
    description: 'Log₁₀ microbial population at each time point',
    unit: 'log CFU/g or log CFU/mL',
    families: ['kinetic', 'survival'], required: ['kinetic'],
  },
  // ── Survival required ────────────────────────────────────────────────────
  {
    id: 'event', label: 'Event / Censoring indicator',
    description: '1 = failure/rejection occurred · 0 = observation censored',
    families: ['survival'], required: ['survival'],
  },
  // ── Shared optional ──────────────────────────────────────────────────────
  {
    id: 'temperature', label: 'Temperature',
    description: 'Storage or treatment temperature',
    unit: '°C', families: ['kinetic', 'survival'], required: [],
  },
  {
    id: 'pH', label: 'pH',
    description: 'Product pH (typically 3–8)',
    families: ['kinetic', 'survival'], required: [],
  },
  {
    id: 'aw', label: 'Water activity (aW)',
    description: 'Water activity (0–1)',
    families: ['kinetic', 'survival'], required: [],
  },
  {
    id: 'preservative', label: 'Preservative / Treatment',
    description: 'Preservative type, antimicrobial agent, or treatment label',
    families: ['kinetic', 'survival'], required: [],
  },
  {
    id: 'concentration', label: 'Concentration / Dose',
    description: 'Preservative or inhibitor dose',
    unit: 'ppm, mg/kg, or mg/L', families: ['kinetic', 'survival'], required: [],
  },
  {
    id: 'packaging', label: 'Packaging',
    description: 'Packaging atmosphere (MAP, vacuum, air, modified)',
    families: ['kinetic', 'survival'], required: [],
  },
  {
    id: 'microorganism', label: 'Microorganism',
    description: 'Target organism name or code',
    families: ['kinetic', 'survival'], required: [],
  },
  {
    id: 'product_type', label: 'Product type',
    description: 'Specific product name (e.g. Brie, chicken breast)',
    families: ['kinetic', 'survival'], required: [],
  },
  {
    id: 'product_category', label: 'Product category',
    description: 'Broad food category (e.g. cheese, meat, RTE)',
    families: ['kinetic', 'survival'], required: [],
  },
  {
    id: 'control_indicator', label: 'Control indicator',
    description: 'Flags control group rows (1 = control, 0 = treatment)',
    families: ['kinetic', 'survival'], required: [],
  },
  {
    id: 'study_id', label: 'Study / Source ID',
    description: 'Study or paper identifier for hierarchical grouping',
    families: ['kinetic', 'survival'], required: [],
  },
  {
    id: 'replicate', label: 'Replicate',
    description: 'Replicate or trial number',
    families: ['kinetic', 'survival'], required: [],
  },
  // ── Kinetic optional ─────────────────────────────────────────────────────
  {
    id: 'failure_threshold', label: 'Failure threshold',
    description: 'Log₁₀ count at which the product is considered failed',
    unit: 'log CFU/g', families: ['kinetic'], required: [],
  },
  {
    id: 'measurement_stage', label: 'Measurement stage / type',
    description: 'Stage or category of the measurement (e.g. rind, core, surface)',
    families: ['kinetic'], required: [],
  },
  {
    id: 'treatment', label: 'Treatment group',
    description: 'Experimental group or condition label',
    families: ['kinetic'], required: [],
  },
  // ── Survival optional ────────────────────────────────────────────────────
  {
    id: 'additional_predictor', label: 'Additional predictor',
    description: 'Any other predictor column to include in the model',
    families: ['survival'], required: [],
  },
]

export const ROLE_MAP: Record<string, ColumnRole> = Object.fromEntries(
  ROLES.map(r => [r.id, r])
)

// ─── Aliases ─────────────────────────────────────────────────────────────────
export const ALIASES: Record<string, string[]> = {
  trajectory_id: [
    'trajectory', 'traj', 'trajectory_id', 'experiment_id', 'exp_id',
    'curve_id', 'curve', 'series', 'series_id', 'run_id', 'sample_id',
    'sample', 'id', 'batch_id', 'batch',
  ],
  time: [
    'time', 'day', 'days', 'storage_day', 'storage_days', 'duration',
    'hours', 'hour', 'minutes', 'min', 'storage_time', 'observation_time',
    't_h', 'time_h', 'time_days', 'time_hours', 'age', 'sampling_time',
    'exposure_time', 'incubation_time', 't',
  ],
  event: [
    'event', 'status', 'failure', 'failure_occurred', 'failed',
    'spoiled', 'rejected', 'outcome', 'censored', 'indicator',
    'shelf_life_reached', 'exceeded', 'spoilage', 'censor',
  ],
  response: [
    'count', 'log_cfu', 'log_count', 'microbial_value', 'log_cfu_g',
    'log_cfu_ml', 'cfu', 'bacterial_count', 'microbial_count',
    'population', 'log_n', 'nt', 'n_t', 'log_population', 'response',
    'cell_count', 'concentration_log', 'logcfu', 'log10_cfu', 'y',
  ],
  temperature: [
    'temp', 'temperature', 'storage_temperature', 'temp_c',
    'temperature_c', 'storage_temp', 't_storage', 'incubation_temp',
    'storage_t', 'treatment_temp',
  ],
  pH: ['ph', 'acidity', 'hydrogen_ion', 'ph_value', 'initial_ph'],
  aw: [
    'aw', 'water_activity', 'a_w', 'moisture', 'water_content',
    'water_act', 'activity',
  ],
  preservative: [
    'preservative', 'antimicrobial', 'additive', 'agent', 'bacteriocin',
    'treatment_type', 'inhibitor', 'substance', 'ingredient',
  ],
  concentration: [
    'concentration', 'dose', 'conc', 'level', 'amount',
    'ppm', 'mg_kg', 'mg_l', 'mg_ml', 'iu_ml',
  ],
  packaging: [
    'packaging', 'package', 'atmosphere', 'map', 'packaging_type',
    'modified_atmosphere', 'gas', 'pack',
  ],
  microorganism: [
    'microorganism', 'organism', 'bacteria', 'pathogen', 'species',
    'strain', 'target_organism', 'micro',
  ],
  product_type: [
    'product', 'product_name', 'food', 'food_type', 'product_type',
    'item', 'matrix', 'product_description',
  ],
  product_category: [
    'category', 'product_category', 'food_category', 'food_group',
    'type', 'class',
  ],
  control_indicator: [
    'control', 'is_control', 'control_indicator', 'ctrl',
  ],
  study_id: [
    'study', 'study_id', 'paper', 'paper_id', 'source',
    'reference', 'dataset_id', 'publication',
  ],
  replicate: [
    'replicate', 'rep', 'replication', 'trial', 'run',
    'repeat', 'repetition',
  ],
  failure_threshold: [
    'threshold', 'failure_threshold', 'limit', 'critical_level',
    'acceptance_limit', 'regulatory_limit',
  ],
  measurement_stage: [
    'stage', 'measurement_stage', 'location', 'sampling_location',
    'site', 'position', 'layer',
  ],
  treatment: [
    'treatment', 'group', 'condition', 'sample_type', 'formulation',
    'treatment_group', 'trt', 'grp',
  ],
  additional_predictor: [
    'predictor', 'covariate', 'feature', 'variable', 'factor',
  ],
}

// ─── Type detection ───────────────────────────────────────────────────────────
export function detectDataType(values: string[]): DataType {
  const nonEmpty = values.filter(v => v !== '' && v != null)
  if (nonEmpty.length === 0) return 'text'
  const boolSet = new Set(['0', '1', 'true', 'false', 'yes', 'no'])
  if (nonEmpty.every(v => boolSet.has(v.toLowerCase()))) return 'boolean'
  const numericCount = nonEmpty.filter(v => v !== '' && isFinite(Number(v))).length
  if (numericCount / nonEmpty.length >= 0.80) return 'numeric'
  const unique = new Set(nonEmpty)
  if (unique.size <= 20 && unique.size <= nonEmpty.length * 0.5) return 'categorical'
  return 'text'
}

function normalise(s: string): string {
  return s
    .toLowerCase()
    .replace(/\s+/g, '_')
    .replace(/[()[\]{}]/g, '')
    .replace(/[^a-z0-9_]/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '')
}

export function suggestRole(
  columnName: string,
  dataType: DataType,
  sampleValues: string[],
  family: ModelFamily,
): RoleId {
  const norm = normalise(columnName)
  for (const [roleId, aliases] of Object.entries(ALIASES)) {
    for (const alias of aliases) {
      if (norm === alias || norm.includes(alias) || alias.includes(norm)) {
        const role = ROLE_MAP[roleId]
        if (role && role.families.includes(family)) return roleId as RoleId
      }
    }
  }
  // Heuristic fallbacks
  if (dataType === 'boolean' && family === 'survival') return 'event'
  if (dataType === 'numeric') {
    const nums = sampleValues.map(Number).filter(isFinite)
    if (nums.length > 0) {
      const avg = nums.reduce((a, b) => a + b, 0) / nums.length
      if (avg >= 1 && avg <= 12 && family === 'kinetic') return 'response'
    }
  }
  if (dataType === 'categorical' && family === 'kinetic') return 'treatment'
  if (dataType === 'categorical' && family === 'survival') return 'preservative'
  return 'unassigned'
}

export function detectDatasetType(
  headers: string[],
  rows: string[][],
): { type: 'kinetic' | 'survival' | 'unknown'; confidence: 'high' | 'medium' | 'low' } {
  const norms = headers.map(normalise)
  let survivalScore = 0
  let kineticScore = 0

  for (const norm of norms) {
    for (const a of ALIASES.event)         if (norm === a || norm.includes(a)) { survivalScore += 3; break }
    for (const a of ALIASES.response)      if (norm === a || norm.includes(a)) { kineticScore  += 2; break }
    for (const a of ALIASES.trajectory_id) if (norm === a || norm.includes(a)) { kineticScore  += 2; break }
    for (const a of ALIASES.study_id)      if (norm === a || norm.includes(a)) { survivalScore += 1; break }
    for (const a of ALIASES.replicate)     if (norm === a || norm.includes(a)) { kineticScore  += 1; break }
  }

  // 0/1 column → survival event indicator
  for (let ci = 0; ci < headers.length; ci++) {
    const vals = rows.slice(0, 20).map(r => r[ci] ?? '')
    if (detectDataType(vals) === 'boolean') survivalScore += 2
  }

  const total = survivalScore + kineticScore
  if (total === 0) return { type: 'unknown', confidence: 'low' }
  if (survivalScore > kineticScore) {
    return { type: 'survival', confidence: survivalScore >= 5 ? 'high' : 'medium' }
  }
  return { type: 'kinetic', confidence: kineticScore >= 4 ? 'high' : 'medium' }
}

export function getRequiredRoles(family: ModelFamily): RoleId[] {
  return ROLES.filter(r => r.required.includes(family)).map(r => r.id as RoleId)
}

export function getOptionalRoles(family: ModelFamily): RoleId[] {
  return ROLES.filter(r => r.families.includes(family) && !r.required.includes(family))
    .map(r => r.id as RoleId)
}

// ─── CSV Templates ────────────────────────────────────────────────────────────
export const KINETIC_TEMPLATE_ROWS = [
  ['trajectory_id', 'time_h', 'log_cfu_g', 'temperature_C', 'pH', 'aw', 'treatment', 'replicate', 'failure_threshold'],
  ['EXP_001', '0',  '3.50', '4',  '6.2', '0.97', 'nisin_2ppm', '1', '7.0'],
  ['EXP_001', '6',  '3.80', '4',  '6.2', '0.97', 'nisin_2ppm', '1', '7.0'],
  ['EXP_001', '12', '4.20', '4',  '6.2', '0.97', 'nisin_2ppm', '1', '7.0'],
  ['EXP_001', '24', '5.10', '4',  '6.2', '0.97', 'nisin_2ppm', '1', '7.0'],
  ['EXP_001', '36', '6.80', '4',  '6.2', '0.97', 'nisin_2ppm', '1', '7.0'],
  ['EXP_002', '0',  '3.50', '4',  '6.2', '0.97', 'control',    '1', '7.0'],
  ['EXP_002', '6',  '4.30', '4',  '6.2', '0.97', 'control',    '1', '7.0'],
  ['EXP_002', '12', '5.80', '4',  '6.2', '0.97', 'control',    '1', '7.0'],
  ['EXP_002', '24', '7.20', '4',  '6.2', '0.97', 'control',    '1', '7.0'],
]

export const SURVIVAL_TEMPLATE_ROWS = [
  ['time_days', 'event', 'temperature_C', 'pH', 'aw', 'preservative', 'concentration_ppm', 'packaging', 'product_category'],
  ['14', '1', '4',  '6.2', '0.97', 'nisin',    '2.5', 'MAP',    'cheese'],
  ['21', '0', '4',  '6.2', '0.97', 'nisin',    '2.5', 'MAP',    'cheese'],
  ['28', '0', '4',  '6.2', '0.97', 'nisin',    '2.5', 'MAP',    'cheese'],
  ['7',  '1', '10', '5.8', '0.95', 'control',  '0',   'Air',    'meat'],
  ['10', '1', '10', '5.8', '0.95', 'control',  '0',   'Air',    'meat'],
  ['14', '0', '10', '5.8', '0.95', 'natamycin','5.0', 'MAP',    'meat'],
  ['21', '0', '10', '5.8', '0.95', 'natamycin','5.0', 'MAP',    'meat'],
]
