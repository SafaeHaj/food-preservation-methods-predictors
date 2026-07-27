/**
 * Canonical scientific data: studies, experiments, treatment arms, observations,
 * trajectories, thresholds, imputations, normalization, microorganisms, audit.
 *
 * Every list query is project-scoped. The server now scopes them too — omitting a project
 * id used to return the whole table — but passing it keeps each cache entry addressed by
 * the project it belongs to, so switching projects cannot show stale rows from the last one.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, patch, post } from './client'
import { keys } from './keys'
import { config } from '../config'
import type {
  AuditEvent, Experiment, ImputationProposal, Microorganism, ModelRun,
  NormalizationMapping, Observation, Study, Threshold, Trajectory, TreatmentArm,
} from '../types'

// ─── Studies ──────────────────────────────────────────────────────────────────

export function useStudies(projectId: number, filters: { review_status?: string } = {}) {
  const params = { project_id: projectId, ...filters }
  return useQuery({
    queryKey: keys.studies.list(projectId, filters),
    queryFn: () => get<Study[]>('/studies', params),
    enabled: Number.isFinite(projectId),
  })
}

export function useStudyMutations(projectId: number) {
  const queryClient = useQueryClient()
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: keys.studies.all(projectId) })
    queryClient.invalidateQueries({ queryKey: keys.projects.stats(projectId) })
  }

  return {
    create: useMutation({
      mutationFn: (body: Record<string, unknown>) => post<Study>('/studies', body),
      onSuccess: invalidate,
    }),
    approve: useMutation({
      mutationFn: ({ id, reason }: { id: number; reason?: string }) =>
        post<Study>(`/studies/${id}/approve${reason ? `?reason=${encodeURIComponent(reason)}` : ''}`),
      onSuccess: invalidate,
    }),
    reject: useMutation({
      mutationFn: ({ id, reason }: { id: number; reason?: string }) =>
        post<Study>(`/studies/${id}/reject${reason ? `?reason=${encodeURIComponent(reason)}` : ''}`),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: number) => del(`/studies/${id}`),
      onSuccess: invalidate,
    }),
  }
}

// ─── Experiments ──────────────────────────────────────────────────────────────

export function useExperiments(
  projectId: number,
  filters: { study_id?: number; limit?: number } = {},
) {
  const params = { project_id: projectId, limit: config.pageSize.default, ...filters }
  return useQuery({
    queryKey: keys.experiments.list(projectId, params),
    queryFn: () => get<Experiment[]>('/experiments', params),
    enabled: Number.isFinite(projectId),
  })
}

export function useCreateExperiment(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => post<Experiment>('/experiments', body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.experiments.all(projectId) }),
  })
}

// ─── Treatment arms ───────────────────────────────────────────────────────────

/**
 * Every arm in a project, in one request.
 *
 * The treatments page used to fetch 500 experiments and then issue one arm request per
 * experiment — 501 round trips to render one table. The `project_id` filter was added to
 * the endpoint specifically to collapse that.
 */
export function useTreatmentArms(
  projectId: number,
  filters: { experiment_id?: number; limit?: number } = {},
) {
  const params = { project_id: projectId, limit: config.pageSize.observations, ...filters }
  return useQuery({
    queryKey: keys.arms.list(projectId, params),
    queryFn: () => get<TreatmentArm[]>('/treatment-arms', params),
    enabled: Number.isFinite(projectId),
  })
}

// ─── Observations ─────────────────────────────────────────────────────────────

export interface ObservationFilters {
  treatment_arm_id?: number
  experiment_id?: number
  measurement_type?: string
  review_status?: string
  include_imputed?: boolean
  limit?: number
}

export function useObservations(projectId: number, filters: ObservationFilters = {}) {
  const params = { project_id: projectId, limit: config.pageSize.observations, ...filters }
  return useQuery({
    queryKey: keys.observations.list(projectId, params),
    queryFn: () => get<Observation[]>('/observations', params),
    enabled: Number.isFinite(projectId),
  })
}

// ─── Trajectories ─────────────────────────────────────────────────────────────

export function useTrajectories(
  projectId: number,
  filters: { process_class?: string; data_sufficient?: boolean } = {},
) {
  const params = { project_id: projectId, ...filters }
  return useQuery({
    queryKey: keys.trajectories.list(projectId, filters),
    queryFn: () => get<Trajectory[]>('/trajectories', params),
    enabled: Number.isFinite(projectId),
  })
}

export function useTrajectoryRuns(trajectoryId: number | null) {
  return useQuery({
    queryKey: keys.trajectories.runs(trajectoryId ?? 0),
    queryFn: () => get<ModelRun[]>(`/trajectories/${trajectoryId}/runs`),
    enabled: trajectoryId !== null,
  })
}

export function useFitTrajectory(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (trajectoryId: number) => post<ModelRun>(`/trajectories/${trajectoryId}/fit`),
    onSuccess: (_run, trajectoryId) => {
      queryClient.invalidateQueries({ queryKey: keys.trajectories.runs(trajectoryId) })
      queryClient.invalidateQueries({ queryKey: keys.trajectories.all(projectId) })
    },
  })
}

// ─── Thresholds ───────────────────────────────────────────────────────────────

export function useThresholds(projectId: number) {
  return useQuery({
    queryKey: keys.thresholds.list(projectId),
    queryFn: () => get<Threshold[]>('/thresholds', { project_id: projectId }),
    enabled: Number.isFinite(projectId),
  })
}

export function useThresholdMutations(projectId: number) {
  const queryClient = useQueryClient()
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: keys.thresholds.all(projectId) })

  return {
    create: useMutation({
      mutationFn: (body: Record<string, unknown>) =>
        post<Threshold>('/thresholds', { ...body, project_id: projectId }),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: number) => del(`/thresholds/${id}`),
      onSuccess: invalidate,
    }),
  }
}

export function useThresholdCrossings(thresholdId: number | null, projectId: number) {
  return useQuery({
    queryKey: keys.thresholds.crossings(thresholdId ?? 0, projectId),
    queryFn: () =>
      get<unknown>(`/thresholds/${thresholdId}/crossings`, { project_id: projectId }),
    enabled: thresholdId !== null,
  })
}

// ─── Imputations ──────────────────────────────────────────────────────────────

export function useImputations(
  projectId: number,
  filters: { reviewer_decision?: string } = {},
) {
  const params = { project_id: projectId, ...filters }
  return useQuery({
    queryKey: keys.imputations.list(projectId, filters),
    queryFn: () => get<ImputationProposal[]>('/imputations', params),
    enabled: Number.isFinite(projectId),
  })
}

export function useReviewImputation(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, decision, note }: {
      id: number
      decision: 'accepted' | 'rejected'
      note?: string
    }) => post<ImputationProposal>(`/imputations/${id}/review`, { decision, note }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.imputations.all(projectId) })
      // Accepting an imputation writes an observation, so the dataset view is now stale.
      queryClient.invalidateQueries({ queryKey: keys.observations.all(projectId) })
    },
  })
}

// ─── Normalization ────────────────────────────────────────────────────────────

export function useNormalizationMappings(projectId: number) {
  return useQuery({
    queryKey: keys.normalization.mappings(projectId),
    queryFn: () =>
      get<NormalizationMapping[]>('/normalization/mappings', { project_id: projectId }),
    enabled: Number.isFinite(projectId),
  })
}

export function useNormalizationMutations(projectId: number) {
  const queryClient = useQueryClient()
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: keys.normalization.all(projectId) })

  return {
    create: useMutation({
      mutationFn: (body: Record<string, unknown>) =>
        post<NormalizationMapping>('/normalization/mappings', {
          ...body,
          project_id: projectId,
          source: 'manual',
        }),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: number) => del(`/normalization/mappings/${id}`),
      onSuccess: invalidate,
    }),
    apply: useMutation({
      mutationFn: () => post<{ updated: number }>(`/normalization/apply/${projectId}`),
      onSuccess: () => {
        invalidate()
        // Applying mappings rewrites normalized values across the dataset.
        queryClient.invalidateQueries({ queryKey: keys.observations.all(projectId) })
      },
    }),
  }
}

// ─── Microorganisms ───────────────────────────────────────────────────────────

export function useMicroorganisms(projectId: number) {
  return useQuery({
    queryKey: keys.microorganisms.list(projectId),
    queryFn: () => get<Microorganism[]>('/microorganisms', { project_id: projectId }),
    enabled: Number.isFinite(projectId),
  })
}

// ─── Audit ────────────────────────────────────────────────────────────────────

export function useAuditEvents(
  projectId: number,
  filters: { entity_type?: string; action?: string; limit?: number } = {},
) {
  const params = { project_id: projectId, limit: config.pageSize.default, ...filters }
  return useQuery({
    queryKey: keys.audit.list(projectId, filters),
    queryFn: () => get<AuditEvent[]>('/audit', params),
    enabled: Number.isFinite(projectId),
  })
}

// ─── Snapshots and exports ────────────────────────────────────────────────────

export function useSnapshots(projectId: number) {
  return useQuery({
    queryKey: keys.snapshots.all(projectId),
    queryFn: () => get<unknown[]>('/snapshots', { project_id: projectId }),
    enabled: Number.isFinite(projectId),
  })
}

export function useRequestExport(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { format: string; snapshot_id?: number }) =>
      post<{ id: number; status: string }>('/snapshots/export', {
        ...body,
        project_id: projectId,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.snapshots.all(projectId) }),
  })
}

export function useExportRun(runId: number | null) {
  return useQuery({
    queryKey: keys.snapshots.exportRun(runId ?? 0),
    queryFn: () => get<{ id: number; status: string; file_path?: string }>(
      `/snapshots/exports/${runId}`,
    ),
    enabled: runId !== null,
    // Exports are not job-backed, so this is the one place a poll is still correct. It
    // stops on its own the moment the run reaches a terminal state.
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'completed' || status === 'failed' ? false : config.jobPollFallbackMs
    },
  })
}
