import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { trajectoriesApi } from '../../services/api'
import type { Trajectory, ModelRun } from '../../types'
import { Play, RefreshCw, Cpu } from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'

const PROCESS_COLORS: Record<string, string> = {
  growth: 'bg-green-100 text-green-800',
  inactivation: 'bg-red-100 text-red-800',
  stable: 'bg-gray-100 text-gray-700',
  insufficient_data: 'bg-yellow-100 text-yellow-700',
}

export default function TrajectoriesPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [trajectories, setTrajectories] = useState<Trajectory[]>([])
  const [loading, setLoading] = useState(true)
  const [fittingId, setFittingId] = useState<number | null>(null)
  const [processFilter, setProcessFilter] = useState('')

  const load = () => {
    if (!projectId) return
    setLoading(true)
    trajectoriesApi.list({ project_id: Number(projectId), process_class: processFilter || undefined })
      .then(setTrajectories)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [projectId, processFilter])

  const handleFit = async (id: number) => {
    setFittingId(id)
    try {
      const run: ModelRun = await trajectoriesApi.fitModels(id)
      toast.success(`Model fitting started (run #${run.id})`)
    } catch {
      toast.error('Failed to start fitting')
    } finally {
      setFittingId(null)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Trajectories</h1>
        <div className="flex gap-2">
          <select className="border border-gray-300 rounded px-2 py-1 text-sm" value={processFilter} onChange={(e) => setProcessFilter(e.target.value)}>
            <option value="">All process classes</option>
            <option value="growth">Growth</option>
            <option value="inactivation">Inactivation</option>
            <option value="stable">Stable</option>
            <option value="insufficient_data">Insufficient data</option>
          </select>
          <button onClick={load} className="flex items-center gap-1 text-sm text-gray-600 border border-gray-300 rounded px-2 py-1">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      <div className="mb-3 text-sm text-gray-500">
        Trajectories group observations with the same conditions into temporal series ready for model fitting.
      </div>

      {loading ? (
        <p className="text-gray-500 text-sm">Loading…</p>
      ) : trajectories.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <p>No trajectories yet.</p>
          <p className="text-sm mt-1">They are built automatically during extraction or can be created manually.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {trajectories.map((t) => (
            <div key={t.id} className="bg-white border border-gray-200 rounded-lg p-4 flex items-center gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-900">{t.label ?? `Trajectory #${t.id}`}</span>
                  {t.process_class && (
                    <span className={clsx('px-2 py-0.5 rounded-full text-xs font-medium', PROCESS_COLORS[t.process_class] ?? 'bg-gray-100 text-gray-600')}>
                      {t.process_class}
                    </span>
                  )}
                  {!t.data_sufficient && (
                    <span className="px-2 py-0.5 rounded-full text-xs bg-orange-100 text-orange-700">insufficient data</span>
                  )}
                </div>
                <p className="text-sm text-gray-500 mt-0.5">
                  {t.measurement_type}
                  {t.measurement_subtype ? ` · ${t.measurement_subtype}` : ''}
                  {' · '}{t.n_points} points
                  {t.time_min_days != null ? ` · ${t.time_min_days}–${t.time_max_days} days` : ''}
                </p>
              </div>
              <button
                onClick={() => handleFit(t.id)}
                disabled={fittingId === t.id || !t.data_sufficient}
                className="flex items-center gap-1 text-sm px-3 py-1.5 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-40"
              >
                <Cpu size={14} />
                {fittingId === t.id ? 'Starting…' : 'Fit Models'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
