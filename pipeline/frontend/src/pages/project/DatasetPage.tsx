import { useEffect, useState, useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { observationsApi } from '../../services/api'
import type { Observation } from '../../types'
import { RefreshCw, Download } from 'lucide-react'

export default function DatasetPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [observations, setObservations] = useState<Observation[]>([])
  const [loading, setLoading] = useState(true)
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [includeImputed, setIncludeImputed] = useState(true)

  const load = () => {
    if (!projectId) return
    setLoading(true)
    observationsApi
      .list({
        project_id: Number(projectId),
        measurement_type: typeFilter || undefined,
        review_status: statusFilter || undefined,
        include_imputed: includeImputed,
        limit: 500,
      })
      .then(setObservations)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [projectId, typeFilter, statusFilter, includeImputed])

  const measurementTypes = useMemo(() => {
    const s = new Set(observations.map((o) => o.measurement_type))
    return Array.from(s).sort()
  }, [observations])

  const handleCsvDownload = () => {
    const header = ['id', 'treatment_arm_id', 'measurement_type', 'time_days', 'numeric_value_normalized', 'unit_normalized', 'review_status', 'value_origin']
    const rows = observations.map((o) =>
      [o.id, o.treatment_arm_id, o.measurement_type, o.time_days, o.numeric_value_normalized, o.unit_normalized, o.review_status, o.value_origin].join(',')
    )
    const blob = new Blob([header.join(',') + '\n' + rows.join('\n')], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `dataset_project_${projectId}.csv`
    a.click()
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Dataset ({observations.length} observations)</h1>
        <div className="flex gap-2">
          <select className="border border-gray-300 rounded px-2 py-1 text-sm" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
            <option value="">All types</option>
            {measurementTypes.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <select className="border border-gray-300 rounded px-2 py-1 text-sm" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All statuses</option>
            <option value="approved">Approved</option>
            <option value="extracted">Extracted</option>
            <option value="needs_review">Needs review</option>
          </select>
          <label className="flex items-center gap-1 text-sm text-gray-600 cursor-pointer">
            <input type="checkbox" checked={includeImputed} onChange={(e) => setIncludeImputed(e.target.checked)} />
            Show imputed
          </label>
          <button onClick={load} className="flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900 px-2 py-1 border border-gray-300 rounded">
            <RefreshCw size={14} />
          </button>
          <button onClick={handleCsvDownload} className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 px-2 py-1 border border-blue-300 rounded">
            <Download size={14} /> CSV
          </button>
        </div>
      </div>

      {loading ? (
        <p className="text-gray-500 text-sm">Loading observations…</p>
      ) : (
        <div className="overflow-x-auto bg-white rounded-lg border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {['ID', 'Arm ID', 'Type', 'Subtype', 'Time (days)', 'Value (normalized)', 'Unit', 'Origin', 'Status', 'Imputed'].map((h) => (
                  <th key={h} className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {observations.slice(0, 200).map((o) => (
                <tr key={o.id} className={`hover:bg-gray-50 ${o.is_imputed ? 'bg-purple-50/30' : ''}`}>
                  <td className="px-3 py-1.5 text-gray-400 text-xs">{o.id}</td>
                  <td className="px-3 py-1.5">{o.treatment_arm_id}</td>
                  <td className="px-3 py-1.5 font-medium">{o.measurement_type}</td>
                  <td className="px-3 py-1.5 text-gray-500">{o.measurement_subtype ?? '—'}</td>
                  <td className="px-3 py-1.5">{o.time_days != null ? o.time_days : '—'}</td>
                  <td className="px-3 py-1.5 font-mono">{o.numeric_value_normalized != null ? o.numeric_value_normalized : '—'}</td>
                  <td className="px-3 py-1.5 text-gray-500">{o.unit_normalized ?? '—'}</td>
                  <td className="px-3 py-1.5">
                    <span className="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600">{o.value_origin}</span>
                  </td>
                  <td className="px-3 py-1.5">
                    <span className={`px-1.5 py-0.5 rounded text-xs ${o.review_status === 'approved' ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
                      {o.review_status}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 text-center">{o.is_imputed ? '✓' : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {observations.length > 200 && (
            <p className="text-xs text-gray-400 text-center py-2">Showing first 200 of {observations.length}. Use Export for full dataset.</p>
          )}
        </div>
      )}
    </div>
  )
}
