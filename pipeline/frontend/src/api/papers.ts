/** Paper queries. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, postForm } from './client'
import { keys } from './keys'
import { config } from '../config'
import type { Paper } from '../types'

export function usePapers(projectId: number) {
  return useQuery({
    queryKey: keys.papers.list(projectId),
    queryFn: () => get<Paper[]>(`/projects/${projectId}/papers`),
    enabled: Number.isFinite(projectId),
    // `paper.status` is the one job-derived field no mounted job stream is guaranteed to be
    // watching: the stream and its `invalidateOnComplete` live only on the workspace page, so
    // starting an extraction and navigating back here would otherwise pin the badge at
    // "Extracting…" forever. Poll only while something is actually mid-extraction, and stop
    // the moment the server reports it done — the same bounded pattern used for export runs.
    refetchInterval: (query) => {
      const papers = query.state.data as Paper[] | undefined
      return papers?.some((paper) => paper.status === 'extracting')
        ? config.jobPollFallbackMs
        : false
    },
  })
}

/**
 * One paper. The workspace uses this instead of scanning the whole list, which is what the
 * page did before — it had no way to name a single paper, so it fetched all of them.
 */
export function usePaper(projectId: number, paperId: number) {
  return useQuery({
    queryKey: keys.papers.detail(projectId, paperId),
    queryFn: () => get<Paper>(`/projects/${projectId}/papers/${paperId}`),
    enabled: Number.isFinite(projectId) && Number.isFinite(paperId),
  })
}

export function useUploadPapers(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (files: File[]) => {
      const form = new FormData()
      files.forEach((file) => form.append('files', file))
      return postForm<Paper[]>(`/projects/${projectId}/papers`, form)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.papers.all(projectId) })
      queryClient.invalidateQueries({ queryKey: keys.projects.stats(projectId) })
    },
  })
}

export function useDeletePaper(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (paperId: number) => del(`/projects/${projectId}/papers/${paperId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.papers.all(projectId) })
      queryClient.invalidateQueries({ queryKey: keys.projects.stats(projectId) })
    },
  })
}
