/**
<<<<<<< HEAD
<<<<<<< HEAD
 * The scientific schema — the five tables the extraction pipeline produces.
 *
 *   useExperiments     -> GET   /projects/{id}/experiments[?paper_id=]
 *   useExperiment      -> GET   /projects/{id}/experiments/{expId}   (measurements + evidence)
 *   useIngredients     -> GET   /projects/{id}/ingredients
 *   useIndicators      -> GET   /projects/{id}/indicators
 *   useUpdateIndicator -> PATCH /projects/{id}/indicators/{indId}
 *
 * These read the extraction output directly. There used to be a second, reshaped copy of
 * the same science behind a separate set of endpoints; this is now the only one.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, patch } from './client'
import { keys } from './keys'
import { assetUrl } from '../config'
import type {
  ExperimentDetail, ExperimentSummary, Indicator, Ingredient,
} from '../types/science'

const base = (projectId: number) => `/projects/${projectId}`

export function useExperiments(projectId: number, paperId?: number) {
  return useQuery({
    queryKey: keys.science.experiments(projectId, paperId),
    queryFn: () =>
      get<ExperimentSummary[]>(
        `${base(projectId)}/experiments`,
=======
 * The structured five-table extraction output (`ext_*`).
=======
 * The scientific schema — the five tables the extraction pipeline produces.
>>>>>>> 713f430 (	deleted:    misc/LineFormer)
 *
 *   useExperiments     -> GET   /projects/{id}/experiments[?paper_id=]
 *   useExperiment      -> GET   /projects/{id}/experiments/{expId}   (measurements + evidence)
 *   useIngredients     -> GET   /projects/{id}/ingredients
 *   useIndicators      -> GET   /projects/{id}/indicators
 *   useUpdateIndicator -> PATCH /projects/{id}/indicators/{indId}
 *
 * These read the extraction output directly. There used to be a second, reshaped copy of
 * the same science behind a separate set of endpoints; this is now the only one.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, patch } from './client'
import { keys } from './keys'
import { assetUrl } from '../config'
import type {
  ExperimentDetail, ExperimentSummary, Indicator, Ingredient,
} from '../types/science'

const base = (projectId: number) => `/projects/${projectId}`

export function useExperiments(projectId: number, paperId?: number) {
  return useQuery({
    queryKey: keys.science.experiments(projectId, paperId),
    queryFn: () =>
      get<ExperimentSummary[]>(
<<<<<<< HEAD
        `${base(projectId)}/food-experiments`,
>>>>>>> 3423b53 (Major changes to fit canonical data schema. Extraction pipeline experimentation in extractor.ipynb (not yet integrated))
=======
        `${base(projectId)}/experiments`,
>>>>>>> 713f430 (	deleted:    misc/LineFormer)
        paperId ? { paper_id: paperId } : undefined,
      ),
    enabled: Number.isFinite(projectId),
  })
}

<<<<<<< HEAD
<<<<<<< HEAD
export function useExperiment(projectId: number, experimentId: number | null) {
  return useQuery({
    queryKey: keys.science.experiment(projectId, experimentId ?? 0),
    queryFn: async () => {
      const detail = await get<ExperimentDetail>(
        `${base(projectId)}/experiments/${experimentId}`,
      )
      // Evidence crops are signed paths, like the workspace's asset links: absolutised here
      // so the <img> that renders them is not resolving against the SPA's own origin.
      return {
        ...detail,
        evidence: detail.evidence.map((item) => ({
          ...item,
          image_url: assetUrl(item.image_url),
          thumbnail_url: assetUrl(item.thumbnail_url),
        })),
      }
    },
=======
export function useFoodExperiment(projectId: number, experimentId: number | null) {
  return useQuery({
    queryKey: keys.extracted.experiment(projectId, experimentId ?? 0),
    queryFn: () =>
      get<ExperimentDetail>(`${base(projectId)}/food-experiments/${experimentId}`),
>>>>>>> 3423b53 (Major changes to fit canonical data schema. Extraction pipeline experimentation in extractor.ipynb (not yet integrated))
=======
export function useExperiment(projectId: number, experimentId: number | null) {
  return useQuery({
    queryKey: keys.science.experiment(projectId, experimentId ?? 0),
    queryFn: async () => {
      const detail = await get<ExperimentDetail>(
        `${base(projectId)}/experiments/${experimentId}`,
      )
      // Evidence crops are signed paths, like the workspace's asset links: absolutised here
      // so the <img> that renders them is not resolving against the SPA's own origin.
      return {
        ...detail,
        evidence: detail.evidence.map((item) => ({
          ...item,
          image_url: assetUrl(item.image_url),
          thumbnail_url: assetUrl(item.thumbnail_url),
        })),
      }
    },
>>>>>>> 713f430 (	deleted:    misc/LineFormer)
    enabled: Number.isFinite(projectId) && experimentId !== null,
  })
}

<<<<<<< HEAD
<<<<<<< HEAD
export function useIngredients(projectId: number) {
  return useQuery({
    queryKey: keys.science.ingredients(projectId),
    queryFn: () => get<Ingredient[]>(`${base(projectId)}/ingredients`),
=======
export function useExtIngredients(projectId: number) {
  return useQuery({
    queryKey: keys.extracted.ingredients(projectId),
    queryFn: () => get<ExtIngredient[]>(`${base(projectId)}/ingredients`),
>>>>>>> 3423b53 (Major changes to fit canonical data schema. Extraction pipeline experimentation in extractor.ipynb (not yet integrated))
=======
export function useIngredients(projectId: number) {
  return useQuery({
    queryKey: keys.science.ingredients(projectId),
    queryFn: () => get<Ingredient[]>(`${base(projectId)}/ingredients`),
>>>>>>> 713f430 (	deleted:    misc/LineFormer)
    enabled: Number.isFinite(projectId),
  })
}

<<<<<<< HEAD
<<<<<<< HEAD
export function useIndicators(projectId: number) {
  return useQuery({
    queryKey: keys.science.indicators(projectId),
    queryFn: () => get<Indicator[]>(`${base(projectId)}/indicators`),
    enabled: Number.isFinite(projectId),
  })
}

/**
 * Set or clear an indicator's threshold.
 *
 * Optimistic, like starring an asset: the edit is a single number in a table the user is
 * reading, and a round trip before the cell updates reads as the click not registering.
 *
 * Invalidates the dataset on settle. A threshold is what makes an indicator labelable, so
 * changing one changes whether the project can be modelled at all — the Model Lab and
 * Prediction screens both key off that count.
 */
export function useUpdateIndicator(projectId: number) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ indicatorId, indicator_threshold }: {
      indicatorId: number
      indicator_threshold: number | null
    }) =>
      patch<Indicator>(`${base(projectId)}/indicators/${indicatorId}`, {
        indicator_threshold,
      }),

    onMutate: async ({ indicatorId, indicator_threshold }) => {
      const key = keys.science.indicators(projectId)
      await queryClient.cancelQueries({ queryKey: key })
      const previous = queryClient.getQueryData<Indicator[]>(key)

      queryClient.setQueryData<Indicator[]>(key, (rows) =>
        rows?.map((row) =>
          row.id === indicatorId ? { ...row, indicator_threshold } : row,
        ),
      )
      return { previous, key }
    },

    onError: (_error, _variables, context) => {
      if (context?.previous) queryClient.setQueryData(context.key, context.previous)
    },

    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: keys.science.all(projectId) })
      queryClient.invalidateQueries({ queryKey: keys.projects.stats(projectId) })
      queryClient.invalidateQueries({ queryKey: keys.dataset.all(projectId) })
    },
  })
}
=======
export function useExtIndicators(projectId: number) {
=======
export function useIndicators(projectId: number) {
>>>>>>> 713f430 (	deleted:    misc/LineFormer)
  return useQuery({
    queryKey: keys.science.indicators(projectId),
    queryFn: () => get<Indicator[]>(`${base(projectId)}/indicators`),
    enabled: Number.isFinite(projectId),
  })
}
<<<<<<< HEAD
>>>>>>> 3423b53 (Major changes to fit canonical data schema. Extraction pipeline experimentation in extractor.ipynb (not yet integrated))
=======

/**
 * Set or clear an indicator's threshold.
 *
 * Optimistic, like starring an asset: the edit is a single number in a table the user is
 * reading, and a round trip before the cell updates reads as the click not registering.
 *
 * Invalidates the dataset on settle. A threshold is what makes an indicator labelable, so
 * changing one changes whether the project can be modelled at all — the Model Lab and
 * Prediction screens both key off that count.
 */
export function useUpdateIndicator(projectId: number) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ indicatorId, indicator_threshold }: {
      indicatorId: number
      indicator_threshold: number | null
    }) =>
      patch<Indicator>(`${base(projectId)}/indicators/${indicatorId}`, {
        indicator_threshold,
      }),

    onMutate: async ({ indicatorId, indicator_threshold }) => {
      const key = keys.science.indicators(projectId)
      await queryClient.cancelQueries({ queryKey: key })
      const previous = queryClient.getQueryData<Indicator[]>(key)

      queryClient.setQueryData<Indicator[]>(key, (rows) =>
        rows?.map((row) =>
          row.id === indicatorId ? { ...row, indicator_threshold } : row,
        ),
      )
      return { previous, key }
    },

    onError: (_error, _variables, context) => {
      if (context?.previous) queryClient.setQueryData(context.key, context.previous)
    },

    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: keys.science.all(projectId) })
      queryClient.invalidateQueries({ queryKey: keys.projects.stats(projectId) })
      queryClient.invalidateQueries({ queryKey: keys.dataset.all(projectId) })
    },
  })
}
>>>>>>> 713f430 (	deleted:    misc/LineFormer)
