/**
 * Observations with missing values, grouped by why they are missing.
 *
 * The query was previously `observationsApi.list({ limit: 500 })` with no project filter,
 * so this page showed — and counted — other projects' gaps as if they were this project's.
 */

import { useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { useObservations } from '../../api/canonical'
import { errorMessage } from '../../api/errors'
import type { MissingReason, Observation } from '../../types'

const MISSING_REASON_LABELS: Record<MissingReason, string> = {
  not_reported: 'Not reported',
  not_measured: 'Not measured',
  not_applicable: 'Not applicable',
  below_detection_limit: 'Below detection limit',
  above_detection_limit: 'Above detection limit',
  unreadable_source: 'Unreadable source',
  extraction_failed: 'Extraction failed',
  removed_after_validation: 'Removed after validation',
  figure_only_not_digitized: 'Figure only, not digitized',
  intentionally_masked_for_validation: 'Intentionally masked',
  unknown: 'Unknown',
}

/** Rows listed per group before collapsing into a count. */
const PREVIEW_PER_GROUP = 5

export default function MissingDataPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { data: allObservations = [], isLoading, error } = useObservations(Number(projectId))

  const missing = useMemo(
    () =>
      allObservations.filter(
        (observation) =>
          observation.missing_reason || observation.numeric_value_normalized == null,
      ),
    [allObservations],
  )

  const byReason = useMemo(
    () =>
      missing.reduce<Record<string, Observation[]>>((groups, observation) => {
        const key = observation.missing_reason ?? 'null_value'
        if (!groups[key]) groups[key] = []
        groups[key].push(observation)
        return groups
      }, {}),
    [missing],
  )

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Missing Data</h1>
        <span className="text-sm text-gray-500">
          {missing.length} observations with missing values
        </span>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-500">Loading…</p>
      ) : error ? (
        <div className="text-center py-12 text-red-500 text-sm">
          {errorMessage(error, 'Could not load observations')}
        </div>
      ) : missing.length === 0 ? (
        <div className="text-center py-12 text-green-600">No missing values found.</div>
      ) : (
        <div className="space-y-4">
          {Object.entries(byReason)
            .sort((a, b) => b[1].length - a[1].length)
            .map(([reason, observations]) => (
              <div key={reason} className="bg-white border border-gray-200 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-sm font-semibold text-gray-800">
                    {MISSING_REASON_LABELS[reason as MissingReason] ?? reason}
                  </h2>
                  <span className="text-sm text-gray-400">
                    {observations.length} observations
                  </span>
                </div>
                <div className="space-y-1">
                  {observations.slice(0, PREVIEW_PER_GROUP).map((observation) => (
                    <div key={observation.id} className="text-xs text-gray-500">
                      Obs #{observation.id} · {observation.measurement_type} ·{' '}
                      t={observation.time_days ?? '?'} days · arm #{observation.treatment_arm_id}
                    </div>
                  ))}
                  {observations.length > PREVIEW_PER_GROUP && (
                    <p className="text-xs text-gray-400">
                      …and {observations.length - PREVIEW_PER_GROUP} more
                    </p>
                  )}
                </div>
              </div>
            ))}
        </div>
      )}
    </div>
  )
}
