/**
 * The structured five-table extraction output (`ext_*`).
 *
 *   useFoodExperiments  -> GET /projects/{id}/food-experiments[?paper_id=]
 *   useFoodExperiment   -> GET /projects/{id}/food-experiments/{expId}   (measurements + evidence)
 *   useExtIngredients   -> GET /projects/{id}/ingredients
 *   useExtIndicators    -> GET /projects/{id}/indicators
 *
 * These endpoints have existed on the extraction service since the pipeline was written;
 * this is the first client to call them. They read the raw LLM output, so nothing here
 * touches the canonical hierarchy the promoter builds from the same rows.
 */

import { useQuery } from '@tanstack/react-query'
import { get } from './client'
import { keys } from './keys'
import type {
  ExperimentDetail, ExperimentSummary, ExtIndicator, ExtIngredient,
} from '../types/extracted'

const base = (projectId: number) => `/projects/${projectId}`

export function useFoodExperiments(projectId: number, paperId?: number) {
  return useQuery({
    queryKey: keys.extracted.experiments(projectId, paperId),
    queryFn: () =>
      get<ExperimentSummary[]>(
        `${base(projectId)}/food-experiments`,
        paperId ? { paper_id: paperId } : undefined,
      ),
    enabled: Number.isFinite(projectId),
  })
}

export function useFoodExperiment(projectId: number, experimentId: number | null) {
  return useQuery({
    queryKey: keys.extracted.experiment(projectId, experimentId ?? 0),
    queryFn: () =>
      get<ExperimentDetail>(`${base(projectId)}/food-experiments/${experimentId}`),
    enabled: Number.isFinite(projectId) && experimentId !== null,
  })
}

export function useExtIngredients(projectId: number) {
  return useQuery({
    queryKey: keys.extracted.ingredients(projectId),
    queryFn: () => get<ExtIngredient[]>(`${base(projectId)}/ingredients`),
    enabled: Number.isFinite(projectId),
  })
}

export function useExtIndicators(projectId: number) {
  return useQuery({
    queryKey: keys.extracted.indicators(projectId),
    queryFn: () => get<ExtIndicator[]>(`${base(projectId)}/indicators`),
    enabled: Number.isFinite(projectId),
  })
}
