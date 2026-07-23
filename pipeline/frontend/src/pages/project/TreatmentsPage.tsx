import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { armsApi, experimentsApi } from '../../services/api'
import type { TreatmentArm, Experiment } from '../../types'
import { RefreshCw } from 'lucide-react'

export default function TreatmentsPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [arms, setArms] = useState<TreatmentArm[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!projectId) return
    setLoading(true)
    // Fetch all experiments for this project, then all arms
    experimentsApi.list({ project_id: Number(projectId), limit: 500 }).then(async (exps: Experiment[]) => {
      const allArms: TreatmentArm[] = []
      for (const exp of exps.slice(0, 50)) {
        const expArms = await armsApi.list({ experiment_id: exp.id })
        allArms.push(...expArms)
      }
      setArms(allArms)
    }).finally(() => setLoading(false))
  }, [projectId])

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Treatment Arms</h1>
      </div>

      {loading ? (
        <p className="text-sm text-gray-500">Loading…</p>
      ) : arms.length === 0 ? (
        <div className="text-center py-12 text-gray-400">No treatment arms found.</div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {['ID', 'Label', 'Control?', 'Type', 'Ingredient', 'Concentration', 'Method', 'Status'].map((h) => (
                  <th key={h} className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {arms.map((a) => (
                <tr key={a.id} className={`hover:bg-gray-50 ${a.is_control ? 'bg-blue-50/30' : ''}`}>
                  <td className="px-3 py-2 text-gray-400 text-xs">{a.id}</td>
                  <td className="px-3 py-2 font-medium">{a.arm_label ?? '—'}</td>
                  <td className="px-3 py-2 text-center">{a.is_control ? '✓' : ''}</td>
                  <td className="px-3 py-2">{a.treatment_type ?? '—'}</td>
                  <td className="px-3 py-2">{a.ingredient_name_normalized ?? a.ingredient_name_original ?? '—'}</td>
                  <td className="px-3 py-2">
                    {a.concentration_value_normalized != null
                      ? `${a.concentration_value_normalized} ${a.concentration_unit_normalized ?? ''}`
                      : '—'}
                  </td>
                  <td className="px-3 py-2">{a.application_method ?? '—'}</td>
                  <td className="px-3 py-2">
                    <span className="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600">{a.review_status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
