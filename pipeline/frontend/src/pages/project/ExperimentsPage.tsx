import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { experimentsApi, studiesApi } from '../../services/api'
import type { Experiment, Study } from '../../types'
import { RefreshCw, Plus, X, AlertCircle } from 'lucide-react'
import toast from 'react-hot-toast'

interface ExpForm {
  study_id: string
  experiment_label: string
  food_category: string
  product_name_original: string
  storage_temperature_c: string
  storage_duration_days: string
  packaging_type: string
  atmosphere_type: string
}
const EMPTY: ExpForm = { study_id: '', experiment_label: '', food_category: '', product_name_original: '', storage_temperature_c: '', storage_duration_days: '', packaging_type: '', atmosphere_type: '' }

export default function ExperimentsPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [experiments, setExperiments] = useState<Experiment[]>([])
  const [studies, setStudies] = useState<Study[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<ExpForm>(EMPTY)
  const [saving, setSaving] = useState(false)

  const load = () => {
    if (!projectId) return
    setLoading(true)
    setError(null)
    Promise.all([
      experimentsApi.list({ project_id: Number(projectId), limit: 200 }),
      studiesApi.list(Number(projectId)),
    ])
      .then(([exps, studs]) => { setExperiments(exps); setStudies(studs) })
      .catch((e) => setError(e?.response?.data?.detail ?? 'Failed to load experiments'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [projectId])

  const handleCreate = async () => {
    if (!form.study_id) { toast.error('Select a study first'); return }
    setSaving(true)
    try {
      await experimentsApi.create({
        study_id: Number(form.study_id),
        experiment_label: form.experiment_label.trim() || undefined,
        food_category: form.food_category.trim() || undefined,
        product_name_original: form.product_name_original.trim() || undefined,
        storage_temperature_c: form.storage_temperature_c ? Number(form.storage_temperature_c) : undefined,
        storage_duration_days: form.storage_duration_days ? Number(form.storage_duration_days) : undefined,
        packaging_type: form.packaging_type.trim() || undefined,
        atmosphere_type: form.atmosphere_type.trim() || undefined,
      })
      toast.success('Experiment created')
      setShowForm(false)
      setForm(EMPTY)
      load()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to create'
      toast.error(msg)
    } finally {
      setSaving(false)
    }
  }

  const set = (k: keyof ExpForm) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Experiments</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setShowForm((v) => !v)}
            className="flex items-center gap-1 text-sm bg-blue-600 text-white px-3 py-1.5 rounded hover:bg-blue-700"
          >
            <Plus size={14} /> New Experiment
          </button>
          <button onClick={load} className="flex items-center gap-1 text-sm text-gray-600 border border-gray-300 rounded px-2 py-1">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {showForm && (
        <div className="bg-white border border-blue-200 rounded-lg p-4 mb-4 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-medium text-gray-900">New Experiment</h2>
            <button onClick={() => { setShowForm(false); setForm(EMPTY) }} className="text-gray-400 hover:text-gray-600"><X size={16} /></button>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="block text-xs text-gray-500 mb-1">Study *</label>
              <select className="border border-gray-300 rounded px-2 py-1.5 text-sm w-full" value={form.study_id} onChange={set('study_id')}>
                <option value="">— select a study —</option>
                {studies.map((s) => <option key={s.id} value={s.id}>{s.title ?? `Study #${s.id}`}</option>)}
              </select>
              {studies.length === 0 && <p className="text-xs text-amber-600 mt-1">No studies yet — create a study first.</p>}
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Label</label>
              <input className="border border-gray-300 rounded px-2 py-1.5 text-sm w-full" placeholder="e.g. Exp-1" value={form.experiment_label} onChange={set('experiment_label')} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Food category</label>
              <select className="border border-gray-300 rounded px-2 py-1.5 text-sm w-full" value={form.food_category} onChange={set('food_category')}>
                <option value="">— select —</option>
                {['cheese', 'meat', 'poultry', 'seafood', 'dairy', 'produce', 'bakery', 'beverage', 'other'].map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Product name</label>
              <input className="border border-gray-300 rounded px-2 py-1.5 text-sm w-full" placeholder="e.g. Camembert cheese" value={form.product_name_original} onChange={set('product_name_original')} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Storage temp (°C)</label>
              <input type="number" className="border border-gray-300 rounded px-2 py-1.5 text-sm w-full" placeholder="4" value={form.storage_temperature_c} onChange={set('storage_temperature_c')} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Duration (days)</label>
              <input type="number" className="border border-gray-300 rounded px-2 py-1.5 text-sm w-full" placeholder="30" value={form.storage_duration_days} onChange={set('storage_duration_days')} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Packaging</label>
              <input className="border border-gray-300 rounded px-2 py-1.5 text-sm w-full" placeholder="e.g. vacuum, MAP" value={form.packaging_type} onChange={set('packaging_type')} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Atmosphere</label>
              <select className="border border-gray-300 rounded px-2 py-1.5 text-sm w-full" value={form.atmosphere_type} onChange={set('atmosphere_type')}>
                <option value="">— select —</option>
                {['aerobic', 'anaerobic', 'MAP', 'vacuum', 'modified_atmosphere'].map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </div>
          </div>
          <div className="flex gap-2 mt-4">
            <button onClick={handleCreate} disabled={saving} className="bg-blue-600 text-white text-sm px-4 py-1.5 rounded hover:bg-blue-700 disabled:opacity-50">
              {saving ? 'Creating…' : 'Create Experiment'}
            </button>
            <button onClick={() => { setShowForm(false); setForm(EMPTY) }} className="text-sm text-gray-500 px-3 py-1.5 border border-gray-300 rounded hover:bg-gray-50">
              Cancel
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700 flex items-center gap-2">
          <AlertCircle size={14} /> {error}
        </div>
      )}

      {loading ? (
        <p className="text-gray-500 text-sm">Loading…</p>
      ) : experiments.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <p className="text-lg font-medium">No experiments yet</p>
          <p className="text-sm mt-1">Create a study first, then add experiments under it.</p>
        </div>
      ) : (
        <div className="overflow-x-auto bg-white rounded-lg border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {['ID', 'Label', 'Product', 'Category', 'Temp (°C)', 'Duration (d)', 'Packaging', 'Status'].map((h) => (
                  <th key={h} className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {experiments.map((e) => (
                <tr key={e.id} className="hover:bg-gray-50">
                  <td className="px-3 py-2 text-gray-400 text-xs">{e.id}</td>
                  <td className="px-3 py-2 font-medium">{e.experiment_label ?? '—'}</td>
                  <td className="px-3 py-2">{e.product_name_normalized ?? e.product_name_original ?? '—'}</td>
                  <td className="px-3 py-2">{e.food_category ?? '—'}</td>
                  <td className="px-3 py-2">{e.storage_temperature_c != null ? e.storage_temperature_c : '—'}</td>
                  <td className="px-3 py-2">{e.storage_duration_days != null ? e.storage_duration_days : '—'}</td>
                  <td className="px-3 py-2">{e.packaging_type ?? '—'}</td>
                  <td className="px-3 py-2">
                    <span className="px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-700">{e.review_status}</span>
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
