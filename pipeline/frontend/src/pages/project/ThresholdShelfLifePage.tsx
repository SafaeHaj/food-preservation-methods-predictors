import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { thresholdsApi } from '../../services/api'
import type { Threshold } from '../../types'
import { Plus, Trash2, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'

export default function ThresholdShelfLifePage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [thresholds, setThresholds] = useState<Threshold[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [crossings, setCrossings] = useState<Record<number, unknown[]>>({})
  const [form, setForm] = useState({
    name: '', measurement_type: 'microbial_count', threshold_value: 6,
    threshold_unit: 'log CFU/g', comparison_operator: '<=',
    source_type: 'regulation', notes: '',
  })

  const load = () => {
    if (!projectId) return
    setLoading(true)
    thresholdsApi.list({ project_id: Number(projectId) }).then(setThresholds).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [projectId])

  const handleCreate = async () => {
    if (!form.name || !form.measurement_type) {
      toast.error('Name and measurement type required')
      return
    }
    await thresholdsApi.create({ ...form, project_id: Number(projectId), threshold_value: Number(form.threshold_value) })
    toast.success('Threshold created')
    setShowForm(false)
    load()
  }

  const handleDelete = async (id: number) => {
    if (!window.confirm('Delete this threshold?')) return
    await thresholdsApi.delete(id)
    toast.success('Deleted')
    load()
  }

  const handleAnalyze = async (id: number) => {
    if (!projectId) return
    const data = await thresholdsApi.getCrossings(id, Number(projectId))
    setCrossings((prev) => ({ ...prev, [id]: data }))
    toast.success(`Found ${data.length} trajectories analyzed`)
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Thresholds & Shelf-Life</h1>
        <div className="flex gap-2">
          <button onClick={() => setShowForm(!showForm)} className="flex items-center gap-1 text-sm bg-blue-600 text-white px-3 py-1.5 rounded hover:bg-blue-700">
            <Plus size={14} /> Add Threshold
          </button>
          <button onClick={load} className="flex items-center gap-1 text-sm text-gray-600 border border-gray-300 rounded px-2 py-1">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {showForm && (
        <div className="bg-white border border-gray-200 rounded-lg p-4 mb-4 space-y-3">
          <h2 className="text-sm font-semibold">New Threshold</h2>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Name</label>
              <input className="border border-gray-300 rounded px-2 py-1 text-sm w-full" value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. EU Listeria limit" />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Measurement type</label>
              <input className="border border-gray-300 rounded px-2 py-1 text-sm w-full" value={form.measurement_type}
                onChange={(e) => setForm({ ...form, measurement_type: e.target.value })} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Threshold value</label>
              <input type="number" className="border border-gray-300 rounded px-2 py-1 text-sm w-full" value={form.threshold_value}
                onChange={(e) => setForm({ ...form, threshold_value: Number(e.target.value) })} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Operator</label>
              <select className="border border-gray-300 rounded px-2 py-1 text-sm w-full" value={form.comparison_operator}
                onChange={(e) => setForm({ ...form, comparison_operator: e.target.value })}>
                {['<=', '>=', '<', '>'].map((op) => <option key={op} value={op}>{op}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Unit</label>
              <input className="border border-gray-300 rounded px-2 py-1 text-sm w-full" value={form.threshold_unit}
                onChange={(e) => setForm({ ...form, threshold_unit: e.target.value })} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Source type</label>
              <select className="border border-gray-300 rounded px-2 py-1 text-sm w-full" value={form.source_type}
                onChange={(e) => setForm({ ...form, source_type: e.target.value })}>
                {['regulation', 'paper', 'team_defined', 'external_reference'].map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={handleCreate} className="bg-blue-600 text-white text-sm px-3 py-1 rounded hover:bg-blue-700">Save</button>
            <button onClick={() => setShowForm(false)} className="text-sm text-gray-500">Cancel</button>
          </div>
        </div>
      )}

      {loading ? <p className="text-sm text-gray-500">Loading…</p> : thresholds.length === 0 ? (
        <div className="text-center py-12 text-gray-400">No thresholds defined. Add one to compute shelf-life crossings.</div>
      ) : (
        <div className="space-y-3">
          {thresholds.map((t) => (
            <div key={t.id} className="bg-white border border-gray-200 rounded-lg p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-gray-900">{t.name}</p>
                  <p className="text-sm text-gray-500 mt-0.5">
                    {t.measurement_type} {t.comparison_operator} {t.threshold_value} {t.threshold_unit ?? ''}
                    {' · '}{t.source_type}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => handleAnalyze(t.id)} className="text-sm bg-purple-600 text-white px-3 py-1 rounded hover:bg-purple-700">
                    Analyze
                  </button>
                  <button onClick={() => handleDelete(t.id)} className="text-red-400 hover:text-red-600 p-1">
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>

              {crossings[t.id] && (
                <div className="mt-3 border-t border-gray-100 pt-3">
                  <h3 className="text-xs font-semibold text-gray-600 mb-2">Threshold crossings</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-gray-500">
                          <th className="text-left px-2 py-1">Trajectory</th>
                          <th className="text-left px-2 py-1">Crossed?</th>
                          <th className="text-left px-2 py-1">Crossing day</th>
                          <th className="text-left px-2 py-1">Source</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(crossings[t.id] as Array<Record<string, unknown>>).map((c, i) => (
                          <tr key={i} className="border-t border-gray-50">
                            <td className="px-2 py-1">{String(c.trajectory_label ?? `#${c.trajectory_id}`)}</td>
                            <td className="px-2 py-1">{c.threshold_crossed ? '✓' : '✗'}</td>
                            <td className="px-2 py-1">{c.crossing_day != null ? `${c.crossing_day} d` : '—'}</td>
                            <td className="px-2 py-1 text-gray-400">{String(c.source ?? '')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
