/**
 * Extraction workspace queries.
 *
 * The request lifecycle this file encodes is the whole point of the refactor:
 *
 *   usePaper            -> GET  /projects/{id}/papers/{paperId}
 *   useStartExtraction  -> POST /projects/{id}/papers/{paperId}/workspace  -> { job_id }
 *   useJobStream        -> SSE  /jobs/{job_id}/events
 *   useAssets(enabled)  -> GET  /projects/{id}/papers/{paperId}/assets     (once, at the end)
 *
 * Four requests and one stream, against roughly forty before. `useAssets` is gated on the
 * job having finished, so nothing asks for results that do not exist yet.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, patch, post } from './client'
import { keys } from './keys'
import { config } from '../config'
import type {
  AssetDetail, AssetPage, EvidencePackages, ExtractionAsset, JobAccepted,
} from '../types/workspace'

const base = (projectId: number, paperId: number) =>
  `/projects/${projectId}/papers/${paperId}`

export interface AssetFilters {
  asset_type?: string
  classification?: string
  skip?: number
  limit?: number
}

export function useAssets(
  projectId: number,
  paperId: number,
  filters: AssetFilters = {},
  options: { enabled?: boolean } = {},
) {
  const params = { limit: config.pageSize.assets, ...filters }
  return useQuery({
    queryKey: keys.workspace.assets(projectId, paperId, params),
    queryFn: () => get<AssetPage>(`${base(projectId, paperId)}/assets`, params),
    // Gated, not conditional-inside-the-component: a disabled query issues no request at
    // all, which is what keeps the asset list from being fetched during extraction.
    enabled: options.enabled !== false && Number.isFinite(projectId) && Number.isFinite(paperId),
  })
}

export function useAsset(projectId: number, paperId: number, assetId: number | null) {
  return useQuery({
    queryKey: keys.workspace.asset(projectId, paperId, assetId ?? 0),
    queryFn: () => get<AssetDetail>(`${base(projectId, paperId)}/assets/${assetId}`),
    enabled: assetId !== null,
  })
}

export function useProjectAssets(projectId: number, filters: AssetFilters = {}) {
  const params = { limit: config.pageSize.assets, ...filters }
  return useQuery({
    queryKey: keys.workspace.projectAssets(projectId, params),
    queryFn: () => get<AssetPage>(`/projects/${projectId}/assets`, params),
    enabled: Number.isFinite(projectId),
  })
}

export function useEvidencePackages(projectId: number, paperId: number, enabled = true) {
  return useQuery({
    queryKey: keys.workspace.evidence(projectId, paperId),
    queryFn: () => get<EvidencePackages>(`${base(projectId, paperId)}/evidence-packages`),
    enabled: enabled && Number.isFinite(projectId) && Number.isFinite(paperId),
  })
}

/** Toggle an asset's LLM selection, or edit its classification/note. */
export function useUpdateAsset(projectId: number, paperId: number) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ assetId, ...body }: {
      assetId: number
      selected_for_llm?: boolean
      classification?: string
      user_note?: string | null
    }) => patch<AssetDetail>(`${base(projectId, paperId)}/assets/${assetId}`, body),

    // Optimistic: starring an asset must feel instant. Every cached asset page for this
    // paper is patched, so the gallery, the filter tabs and the detail panel all move
    // together without any of them refetching.
    onMutate: async ({ assetId, selected_for_llm }) => {
      if (selected_for_llm === undefined) return
      await queryClient.cancelQueries({ queryKey: keys.workspace.all(projectId, paperId) })
      const previous = queryClient.getQueriesData<AssetPage>({
        queryKey: keys.workspace.all(projectId, paperId),
      })

      queryClient.setQueriesData<AssetPage>(
        { queryKey: keys.workspace.all(projectId, paperId) },
        (page) =>
          page?.items
            ? {
                ...page,
                items: page.items.map((asset: ExtractionAsset) =>
                  asset.id === assetId ? { ...asset, selected_for_llm } : asset,
                ),
              }
            : page,
      )
      return { previous }
    },

    onError: (_error, _variables, context) => {
      for (const [key, data] of context?.previous ?? []) {
        queryClient.setQueryData(key, data)
      }
    },

    onSettled: () => {
      // The evidence preview depends on the selection, so it must be recomputed — but
      // only once the mutation settles, not on every render.
      queryClient.invalidateQueries({ queryKey: keys.workspace.evidence(projectId, paperId) })
    },
  })
}

/** Start the Docling pipeline. Returns the job to follow. */
export function useStartExtraction(projectId: number, paperId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => post<JobAccepted>(`${base(projectId, paperId)}/workspace`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.jobs.all() })
    },
  })
}

/** Start LLM ingestion over the curated selection. */
export function useSendToLlm(projectId: number, paperId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => post<JobAccepted>(`${base(projectId, paperId)}/send-to-llm`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.jobs.all() })
    },
  })
}
