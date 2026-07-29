/**
 * The audit log.
 *
 * The one survivor of `api/canonical.ts`, which addressed a scientific hierarchy that no
 * longer exists. Audit events are platform records, not science: they outlive whatever
 * entity they describe, which is the whole point of keeping them.
 */

import { useQuery } from '@tanstack/react-query'
import { get } from './client'
import { keys } from './keys'
import { config } from '../config'
import type { AuditEvent } from '../types'

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
