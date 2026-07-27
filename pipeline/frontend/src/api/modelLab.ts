/** Model-lab queries: datasets, training runs, the model registry and prediction. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, download, get, patch, post, postForm } from './client'
import { keys } from './keys'

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
  results?: Record<string, unknown> | null
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
  model_results: ModelResult[]
  job: {
    status: string
    progress: number
    current_step: string
    error_message: string | null
  } | null
}

export interface PredictResult {
  model_name: string
  predicted_shelf_life_days: number
  ci_lo_days: number | null
  ci_hi_days: number | null
  required_shelf_life_days?: number | null
  success?: boolean | null
  p_success?: number | null
  expected_spoilage_date?: string | null
}

const base = (projectId: number) => `/projects/${projectId}/model-lab`

// ─── Imperative calls ─────────────────────────────────────────────────────────
// The model-lab screens drive an explicit upload -> map -> train wizard where each step is
// a user action with its own progress UI, so they call these directly rather than through
// a query. They still go through the shared client, so auth, the base URL and the error
// envelope are identical; only the caching layer differs.

export const listDatasets = (projectId: number): Promise<BackendDataset[]> =>
  get<BackendDataset[]>(`${base(projectId)}/datasets`)

export const uploadDataset = async (
  projectId: number, file: File, family: string, forceReplace = false,
): Promise<{ duplicate: boolean; dataset: BackendDataset; message?: string }> => {
  const form = new FormData()
  form.append('file', file)
  form.append('dataset_family', family)
  form.append('force_replace', String(forceReplace))
  return postForm(`${base(projectId)}/datasets/upload`, form)
}

export const updateMapping = (
  projectId: number, datasetId: number,
  columnMapping: Record<string, string>, datasetFamily?: string,
): Promise<BackendDataset> =>
  patch<BackendDataset>(`${base(projectId)}/datasets/${datasetId}`, {
    column_mapping: columnMapping,
    dataset_family: datasetFamily,
  })

export const deleteDataset = (projectId: number, datasetId: number): Promise<void> =>
  del(`${base(projectId)}/datasets/${datasetId}`)

export const startTraining = (
  projectId: number, datasetId: number,
  columnMapping: Record<string, string>, datasetFamily: string, threshold?: number,
): Promise<{ training_run_id: number; job_id: number; status: string }> =>
  post(`${base(projectId)}/train`, {
    dataset_id: datasetId,
    column_mapping: columnMapping,
    dataset_family: datasetFamily,
    threshold,
  })

export const listRuns = (projectId: number): Promise<TrainingRunStatus[]> =>
  get<TrainingRunStatus[]>(`${base(projectId)}/runs`)

export const getRun = (projectId: number, runId: number): Promise<TrainingRunStatus> =>
  get<TrainingRunStatus>(`${base(projectId)}/runs/${runId}`)

export const listModels = (projectId: number): Promise<ModelResult[]> =>
  get<ModelResult[]>(`${base(projectId)}/models`)

export const runPrediction = (
  projectId: number, modelId: number, inputFeatures: Record<string, unknown>,
  requiredShelfLife?: number, startDate?: string,
): Promise<PredictResult> =>
  post<PredictResult>(`${base(projectId)}/predict`, {
    model_id: modelId,
    input_features: inputFeatures,
    required_shelf_life: requiredShelfLife,
    start_date: startDate,
  })

// ─── Datasets ─────────────────────────────────────────────────────────────────

export function useDatasets(projectId: number) {
  return useQuery({
    queryKey: keys.modelLab.datasets(projectId),
    queryFn: () => get<BackendDataset[]>(`${base(projectId)}/datasets`),
    enabled: Number.isFinite(projectId),
  })
}

export function useUploadDataset(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ file, family, forceReplace = false }: {
      file: File
      family: string
      forceReplace?: boolean
    }) => {
      const form = new FormData()
      form.append('file', file)
      form.append('dataset_family', family)
      form.append('force_replace', String(forceReplace))
      return postForm<{ duplicate: boolean; dataset: BackendDataset; message?: string }>(
        `${base(projectId)}/datasets/upload`,
        form,
      )
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: keys.modelLab.datasets(projectId) }),
  })
}

export function useUpdateMapping(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ datasetId, columnMapping, datasetFamily }: {
      datasetId: number
      columnMapping: Record<string, string>
      datasetFamily?: string
    }) =>
      patch<BackendDataset>(`${base(projectId)}/datasets/${datasetId}`, {
        column_mapping: columnMapping,
        dataset_family: datasetFamily,
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: keys.modelLab.datasets(projectId) }),
  })
}

export function useDeleteDataset(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (datasetId: number) => del(`${base(projectId)}/datasets/${datasetId}`),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: keys.modelLab.datasets(projectId) }),
  })
}

/**
 * Download a dataset through the axios client so it carries the bearer token and honours
 * the configured API base URL. The previous helper returned a bare `/api/...` string,
 * which bypassed `VITE_API_URL` entirely and broke whenever the gateway was not
 * same-origin.
 */
export const downloadDataset = (projectId: number, datasetId: number, name: string) =>
  download(`${base(projectId)}/datasets/${datasetId}/download`, name)

// ─── Training ─────────────────────────────────────────────────────────────────

export function useTrainingRuns(projectId: number) {
  return useQuery({
    queryKey: keys.modelLab.runs(projectId),
    queryFn: () => get<TrainingRunStatus[]>(`${base(projectId)}/runs`),
    enabled: Number.isFinite(projectId),
  })
}

export function useTrainingRun(projectId: number, runId: number | null) {
  return useQuery({
    queryKey: keys.modelLab.run(projectId, runId ?? 0),
    queryFn: () => get<TrainingRunStatus>(`${base(projectId)}/runs/${runId}`),
    enabled: runId !== null,
  })
}

export function useStartTraining(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      dataset_id: number
      column_mapping: Record<string, string>
      dataset_family: string
      threshold?: number
    }) =>
      post<{ training_run_id: number; job_id: number; status: string }>(
        `${base(projectId)}/train`,
        body,
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.modelLab.runs(projectId) })
      queryClient.invalidateQueries({ queryKey: keys.jobs.all() })
    },
  })
}

// ─── Registry and prediction ──────────────────────────────────────────────────

export function useModels(projectId: number) {
  return useQuery({
    queryKey: keys.modelLab.models(projectId),
    queryFn: () => get<ModelResult[]>(`${base(projectId)}/models`),
    enabled: Number.isFinite(projectId),
  })
}

export function useModel(projectId: number, modelId: number | null) {
  return useQuery({
    queryKey: keys.modelLab.model(projectId, modelId ?? 0),
    queryFn: () => get<ModelResult>(`${base(projectId)}/models/${modelId}`),
    enabled: modelId !== null,
  })
}

export function useDeleteModel(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (modelId: number) => del(`${base(projectId)}/models/${modelId}`),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: keys.modelLab.models(projectId) }),
  })
}

export function usePredict(projectId: number) {
  return useMutation({
    mutationFn: (body: {
      model_id: number
      input_features: Record<string, unknown>
      required_shelf_life?: number
      start_date?: string
    }) => post<PredictResult>(`${base(projectId)}/predict`, body),
  })
}
