import api from './api'

export interface BackendDataset {
  id: number
  project_id: number
  original_name: string
  dataset_family: string | null
  row_count: number
  col_count: number
  headers: string[]
  column_types: Record<string, string>
  column_mapping: Record<string, string>
  parse_status: 'pending' | 'ready' | 'error'
  parse_error: string | null
  file_hash: string | null
  sheet_name: string | null
  uploaded_at: string
  updated_at: string
}

export interface TrainingRunStatus {
  id: number
  project_id: number
  dataset_id: number
  dataset_name: string | null
  job_id: number | null
  dataset_family: string
  n_trajectories: number
  n_fitted: number
  status: 'queued' | 'running' | 'completed' | 'failed'
  error_message: string | null
  created_at: string
  completed_at: string | null
  model_results?: ModelResult[]
  job?: {
    status: string
    progress: number
    current_step: string
    error_message: string | null
  }
}

export interface ModelResult {
  id: number
  training_run_id: number
  model_name: string
  model_family: string
  status: 'pending' | 'training' | 'completed' | 'failed' | 'skipped'
  skip_reason: string | null
  error_message: string | null
  metrics: Record<string, number | null>
  parameters: Record<string, unknown>
  feature_cols: string[]
  target_col: string | null
  mae: number | null
  rmse: number | null
  r_squared: number | null
  concordance_index: number | null
  has_artifact: boolean
  is_active: boolean
  created_at: string
  completed_at: string | null
  results?: Record<string, unknown>  // kinetic trajectory results
}

export interface PredictResult {
  model_name: string
  predicted_shelf_life_days: number
  ci_lo_days: number
  ci_hi_days: number
  required_shelf_life_days?: number
  success?: boolean
  p_success?: number
  expected_spoilage_date?: string
  error?: string
}

// ─── Dataset ──────────────────────────────────────────────────────────────────

export const uploadDataset = async (
  projectId: number,
  file: File,
  family: string,
  forceReplace = false,
): Promise<{ duplicate: boolean; dataset: BackendDataset; message?: string }> => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('dataset_family', family)
  fd.append('force_replace', String(forceReplace))
  const r = await api.post(`/projects/${projectId}/model-lab/datasets/upload`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return r.data
}

export const listDatasets = (projectId: number): Promise<BackendDataset[]> =>
  api.get(`/projects/${projectId}/model-lab/datasets`).then(r => r.data)

export const getDataset = (projectId: number, datasetId: number): Promise<BackendDataset> =>
  api.get(`/projects/${projectId}/model-lab/datasets/${datasetId}`).then(r => r.data)

export const updateMapping = (
  projectId: number,
  datasetId: number,
  columnMapping: Record<string, string>,
  datasetFamily?: string,
): Promise<BackendDataset> =>
  api.patch(`/projects/${projectId}/model-lab/datasets/${datasetId}`, {
    column_mapping: columnMapping,
    dataset_family: datasetFamily,
  }).then(r => r.data)

export const deleteDataset = (projectId: number, datasetId: number): Promise<void> =>
  api.delete(`/projects/${projectId}/model-lab/datasets/${datasetId}`)

export const downloadDatasetUrl = (projectId: number, datasetId: number): string =>
  `/api/projects/${projectId}/model-lab/datasets/${datasetId}/download`

// ─── Training ─────────────────────────────────────────────────────────────────

export const startTraining = (
  projectId: number,
  datasetId: number,
  columnMapping: Record<string, string>,
  datasetFamily: string,
  threshold?: number,
): Promise<{ training_run_id: number; job_id: number; status: string }> =>
  api.post(`/projects/${projectId}/model-lab/train`, {
    dataset_id: datasetId,
    column_mapping: columnMapping,
    dataset_family: datasetFamily,
    threshold,
  }).then(r => r.data)

export const listRuns = (projectId: number): Promise<TrainingRunStatus[]> =>
  api.get(`/projects/${projectId}/model-lab/runs`).then(r => r.data)

export const getRun = (projectId: number, runId: number): Promise<TrainingRunStatus> =>
  api.get(`/projects/${projectId}/model-lab/runs/${runId}`).then(r => r.data)

// ─── Model Registry ───────────────────────────────────────────────────────────

export const listModels = (projectId: number): Promise<ModelResult[]> =>
  api.get(`/projects/${projectId}/model-lab/models`).then(r => r.data)

export const getModel = (projectId: number, modelId: number): Promise<ModelResult> =>
  api.get(`/projects/${projectId}/model-lab/models/${modelId}`).then(r => r.data)

export const deleteModel = (projectId: number, modelId: number): Promise<void> =>
  api.delete(`/projects/${projectId}/model-lab/models/${modelId}`)

// ─── Prediction ───────────────────────────────────────────────────────────────

export const runPrediction = (
  projectId: number,
  modelId: number,
  inputFeatures: Record<string, unknown>,
  requiredShelfLife?: number,
  startDate?: string,
): Promise<PredictResult> =>
  api.post(`/projects/${projectId}/model-lab/predict`, {
    model_id: modelId,
    input_features: inputFeatures,
    required_shelf_life: requiredShelfLife,
    start_date: startDate,
  }).then(r => r.data)
