import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useTrajectories, useTrajectoryRuns } from '../../api/canonical'
import type { Trajectory, ModelRun, ModelFit } from '../../types'
import { RefreshCw, ChevronDown, ChevronUp } from 'lucide-react'
import clsx from 'clsx'

const APPLICABILITY_COLORS: Record<string, string> = {
  green: 'bg-green-100 text-green-800',
  yellow: 'bg-yellow-100 text-yellow-700',
  red: 'bg-red-100 text-red-700',
}

function FitRow({ fit, selected }: { fit: ModelFit; selected: boolean }) {
  return (
    <tr className={clsx('text-sm', selected ? 'bg-blue-50' : 'hover:bg-gray-50')}>
      <td className="px-3 py-2 font-medium">{fit.rank ?? '—'}</td>
      <td className="px-3 py-2">{fit.model_name}</td>
      <td className="px-3 py-2">{fit.converged ? '✓' : '✗'}</td>
      <td className="px-3 py-2">{fit.r_squared != null ? fit.r_squared.toFixed(3) : '—'}</td>
      <td className="px-3 py-2">{fit.rmse != null ? fit.rmse.toFixed(4) : '—'}</td>
      <td className="px-3 py-2">{fit.aic != null ? fit.aic.toFixed(2) : '—'}</td>
      <td className="px-3 py-2">{fit.biological_violations}</td>
      <td className="px-3 py-2">
        {fit.applicability_status && (
          <span className={clsx('px-2 py-0.5 rounded-full text-xs font-medium', APPLICABILITY_COLORS[fit.applicability_status])}>
            {fit.applicability_status}
          </span>
        )}
      </td>
    </tr>
  )
}

function ModelRunCard({ trajId }: { trajId: number }) {
  const [expanded, setExpanded] = useState(false)
  const { data: runs = [] } = useTrajectoryRuns(trajId)

  if (runs.length === 0) return null

  const latest = runs[0]
  return (
    <div className="border border-gray-200 rounded-lg bg-white">
      <button
        className="w-full flex items-center justify-between px-4 py-3 text-sm"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="font-medium">Trajectory #{trajId} — Latest run: {latest.status}</span>
        <span className="text-gray-400 flex items-center gap-1">
          {latest.models_converged}/{latest.models_tried} converged
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </span>
      </button>
      {expanded && (
        <div className="border-t border-gray-100 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                {['Rank', 'Model', 'Converged', 'R²', 'RMSE', 'AIC', 'Bio violations', 'Applicability'].map((h) => (
                  <th key={h} className="px-3 py-2 text-left font-medium text-gray-600 text-xs">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {latest.fits.map((fit) => (
                <FitRow key={fit.id} fit={fit} selected={fit.id === latest.selected_model_id} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function ModelLabPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { data: trajectories = [], isLoading: loading } = useTrajectories(Number(projectId), {
    data_sufficient: true,
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Model Lab</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Gompertz · Baranyi · Logistic · Richards · Log-linear · Weibull · Geeraerd · Biphasic
          </p>
        </div>
      </div>

      {loading ? (
        <p className="text-gray-500 text-sm">Loading…</p>
      ) : trajectories.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <p>No trajectories with sufficient data.</p>
          <p className="text-sm mt-1">Go to Trajectories to build and fit models.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {trajectories.map((t) => (
            <ModelRunCard key={t.id} trajId={t.id} />
          ))}
        </div>
      )}
    </div>
  )
}
