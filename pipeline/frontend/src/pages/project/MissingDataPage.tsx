import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { observationsApi } from '../../services/api'
import type { Observation, MissingReason } from '../../types'
import { RefreshCw } from 'lucide-react'

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

export default function MissingDataPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [observations, setObservations] = useState<Observation[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!projectId) return
    setLoading(true)
    // Fetch observations where missing_reason is set or value is null
    observationsApi.list({ limit: 500 }).then((obs: Observation[]) => {
      setObservations(obs.filter((o) => o.missing_reason || o.numeric_value_normalized == null))
    }).finally(() => setLoading(false))
  }, [projectId])

  const byReason = observations.reduce<Record<string, Observation[]>>((acc, o) => {
    const key = o.missing_reason ?? 'null_value'
    if (!acc[key]) acc[key] = []
    acc[key].push(o)
    return acc
  }, {})

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Missing Data</h1>
        <span className="text-sm text-gray-500">{observations.length} observations with missing values</span>
      </div>

      {loading ? (
        <p className="text-sm text-gray-500">Loading…</p>
      ) : observations.length === 0 ? (
        <div className="text-center py-12 text-green-600">No missing values found.</div>
      ) : (
        <div className="space-y-4">
          {Object.entries(byReason).sort((a, b) => b[1].length - a[1].length).map(([reason, obs]) => (
            <div key={reason} className="bg-white border border-gray-200 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-sm font-semibold text-gray-800">
                  {MISSING_REASON_LABELS[reason as MissingReason] ?? reason}
                </h2>
                <span className="text-sm text-gray-400">{obs.length} observations</span>
              </div>
              <div className="space-y-1">
                {obs.slice(0, 5).map((o) => (
                  <div key={o.id} className="text-xs text-gray-500">
                    Obs #{o.id} · {o.measurement_type} · t={o.time_days ?? '?'} days · arm #{o.treatment_arm_id}
                  </div>
                ))}
                {obs.length > 5 && <p className="text-xs text-gray-400">…and {obs.length - 5} more</p>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
