/** Project and membership queries. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, patch, post } from './client'
import { keys } from './keys'
import type { Project, ProjectMember, ProjectStats } from '../types'

export function useProjects() {
  return useQuery({
    queryKey: keys.projects.list(),
    queryFn: () => get<Project[]>('/projects'),
  })
}

export function useProject(projectId: number) {
  return useQuery({
    queryKey: keys.projects.detail(projectId),
    queryFn: () => get<Project>(`/projects/${projectId}`),
    enabled: Number.isFinite(projectId),
  })
}

/**
 * Project statistics. Deliberately a separate query from the project itself, so a page
 * that only needs the name does not pay for four aggregate counts.
 */
export function useProjectStats(projectId: number, enabled = true) {
  return useQuery({
    queryKey: keys.projects.stats(projectId),
    queryFn: () => get<ProjectStats>(`/projects/${projectId}/stats`),
    enabled: enabled && Number.isFinite(projectId),
  })
}

export function useCreateProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; description?: string }) =>
      post<Project>('/projects', body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.projects.all() }),
  })
}

export function useUpdateProject(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<{ name: string; description: string; schema_fields: unknown[] }>) =>
      patch<Project>(`/projects/${projectId}`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.projects.all() }),
  })
}

export function useDeleteProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (projectId: number) => del(`/projects/${projectId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.projects.all() }),
  })
}

// ─── Members ──────────────────────────────────────────────────────────────────

export function useMembers(projectId: number) {
  return useQuery({
    queryKey: keys.members.all(projectId),
    queryFn: () => get<ProjectMember[]>(`/projects/${projectId}/members`),
    enabled: Number.isFinite(projectId),
  })
}

export function useMemberMutations(projectId: number) {
  const queryClient = useQueryClient()
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: keys.members.all(projectId) })

  return {
    add: useMutation({
      mutationFn: (body: { user_email: string; role: string }) =>
        post<ProjectMember>(`/projects/${projectId}/members`, body),
      onSuccess: invalidate,
    }),
    updateRole: useMutation({
      mutationFn: ({ userId, role }: { userId: number; role: string }) =>
        patch<ProjectMember>(`/projects/${projectId}/members/${userId}`, { role }),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (userId: number) => del(`/projects/${projectId}/members/${userId}`),
      onSuccess: invalidate,
    }),
  }
}
