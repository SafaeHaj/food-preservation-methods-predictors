/**
 * The processed dataset and the prediction surface, both served by the processing service.
 *
 *   useDataset       -> GET  /projects/{id}/dataset
 *   useBuildDataset  -> POST /projects/{id}/dataset/build   -> { job_id }
 *   usePredictionStatus -> GET /projects/{id}/prediction
 *
 * The builder behind these is not written yet: a build reports what it would have consumed
 * and produces no rows. The wiring is real regardless — the screens render the empty
 * result, so what remains is the builder, not the plumbing around it.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from './client'
import { keys } from './keys'
import type { JobAccepted } from '../types/workspace'

const base = (projectId: number) => `/projects/${projectId}`

/** What the project's scientific tables currently hold. */
export interface DatasetSource {
  experiments: number
  ingredients: number
  indicators: number
  measurements: number
  /** Indicators carrying a threshold — without one, nothing can be labelled. */
  indicators_with_threshold: number
}

export interface DatasetPreview {
  project_id: number
  status: 'not_built' | 'not_implemented' | 'ready'
  columns: string[]
  row_count: number
  rows: Record<string, unknown>[]
  source: DatasetSource
}

export interface PredictionStatus {
  project_id: number
  available: boolean
  reason: string
  engines: string[]
  source: DatasetSource
}

export function useDataset(projectId: number) {
  return useQuery({
    queryKey: keys.dataset.preview(projectId),
    queryFn: () => get<DatasetPreview>(`${base(projectId)}/dataset`),
    enabled: Number.isFinite(projectId),
  })
}

export function useBuildDataset(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => post<JobAccepted>(`${base(projectId)}/dataset/build`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.jobs.all() })
    },
  })
}

export function usePredictionStatus(projectId: number) {
  return useQuery({
    queryKey: keys.prediction.status(projectId),
    queryFn: () => get<PredictionStatus>(`${base(projectId)}/prediction`),
    enabled: Number.isFinite(projectId),
  })
}
