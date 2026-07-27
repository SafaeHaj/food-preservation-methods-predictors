/**
 * Treatment arms for a project.
 *
 * This page was the app's worst N+1: it fetched up to 500 experiments and then issued one
 * `GET /treatment-arms?experiment_id=` per experiment — and capped the loop at 50, so the
 * table silently omitted every arm past the fiftieth experiment. The endpoint now accepts
 * a `project_id`, so it is one request and the result is complete.
 */

import { useParams } from 'react-router-dom'
import { useTreatmentArms } from '../../api/canonical'
import { errorMessage } from '../../api/errors'

const COLUMNS = [
  'ID', 'Label', 'Control?', 'Type', 'Ingredient', 'Concentration', 'Method', 'Status',
]

export default function TreatmentsPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { data: arms = [], isLoading, error } = useTreatmentArms(Number(projectId))

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Treatment Arms</h1>
        {arms.length > 0 && <span className="text-sm text-gray-500">{arms.length} arms</span>}
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-500">Loading…</p>
      ) : error ? (
        <div className="text-center py-12 text-red-500 text-sm">
          {errorMessage(error, 'Could not load treatment arms')}
        </div>
      ) : arms.length === 0 ? (
        <div className="text-center py-12 text-gray-400">No treatment arms found.</div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {COLUMNS.map((header) => (
                  <th
                    key={header}
                    className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap"
                  >
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {arms.map((arm) => (
                <tr
                  key={arm.id}
                  className={`hover:bg-gray-50 ${arm.is_control ? 'bg-blue-50/30' : ''}`}
                >
                  <td className="px-3 py-2 text-gray-400 text-xs">{arm.id}</td>
                  <td className="px-3 py-2 font-medium">{arm.arm_label ?? '—'}</td>
                  <td className="px-3 py-2 text-center">{arm.is_control ? '✓' : ''}</td>
                  <td className="px-3 py-2">{arm.treatment_type ?? '—'}</td>
                  <td className="px-3 py-2">
                    {arm.ingredient_name_normalized ?? arm.ingredient_name_original ?? '—'}
                  </td>
                  <td className="px-3 py-2">
                    {arm.concentration_value_normalized != null
                      ? `${arm.concentration_value_normalized} ${arm.concentration_unit_normalized ?? ''}`
                      : '—'}
                  </td>
                  <td className="px-3 py-2">{arm.application_method ?? '—'}</td>
                  <td className="px-3 py-2">
                    <span className="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600">
                      {arm.review_status}
                    </span>
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
