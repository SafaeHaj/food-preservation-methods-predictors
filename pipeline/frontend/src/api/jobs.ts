/** Job queries. Progress streaming lives in `hooks/useJobStream`. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from './client'
import { keys } from './keys'
import type { Job } from '../types'

export interface JobFilters {
  project_id?: number
  paper_id?: number
  status?: string
  job_type?: string
  limit?: number
}

/**
 * Job list.
 *
 * No `refetchInterval`: a running job publishes its own progress over the stream, and the
 * list is invalidated when one finishes. The previous 8-second poll ran for as long as the
 * tab was open, whether or not anything was running.
 */
export function useJobs(filters: JobFilters = {}) {
  return useQuery({
    queryKey: keys.jobs.list(filters),
    queryFn: () => get<Job[]>('/jobs', filters),
  })
}

export function useJob(jobId: number | null) {
  return useQuery({
    queryKey: keys.jobs.detail(jobId ?? 0),
    queryFn: () => get<Job>(`/jobs/${jobId}`),
    enabled: jobId !== null,
  })
}

export function useCancelJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (jobId: number) => post<Job>(`/jobs/${jobId}/cancel`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.jobs.all() }),
  })
}
