import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { normalizationApi } from '../../services/api'
import type { NormalizationMapping } from '../../types'
import { RefreshCw, Play, Trash2, Plus } from 'lucide-react'
import toast from 'react-hot-toast'

export default function NormalizationPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [mappings, setMappings] = useState<NormalizationMapping[]>([])
  const [loading, setLoading] = useState(true)
  const [applying, setApplying] = useState(false)
  const [form, setForm] = useState({ mapping_type: 'cheese_type', original_term: '', canonical_term: '' })
  const [showForm, setShowForm] = useState(false)

  const MAPPING_TYPES = ['cheese_type', 'ingredient', 'microorganism', 'measurement_type', 'application_method', 'packaging', 'unit']

  const load = () => {
    if (!projectId) return
    setLoading(true)
    normalizationApi.listMappings({ project_id: Number(projectId) })
      .then(setMappings)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [projectId])

  const handleApply = async () => {
    if (!projectId) return
    setApplying(true)
    try {
      const result = await normalizationApi.apply(Number(projectId))
      toast.success(`Applied: ${result.experiments} experiments, ${result.observations} observations updated`)
    } catch {
      toast.error('Normalization failed')
    } finally {
      setApplying(false)
    }
  }

  const handleDelete = async (id: number) => {
    await normalizationApi.deleteMapping(id)
    toast.success('Mapping deleted')
    load()
  }

  const handleCreate = async () => {
    if (!form.original_term || !form.canonical_term) {
      toast.error('Both terms required')
      return
    }
    await normalizationApi.createMapping({ ...form, project_id: Number(projectId), source: 'manual' })
    toast.success('Mapping created')
    setShowForm(false)
    setForm({ mapping_type: 'cheese_type', original_term: '', canonical_term: '' })
    load()
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Normalization Mappings</h1>
        <div className="flex gap-2">
          <button onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-1 text-sm bg-blue-600 text-white px-3 py-1.5 rounded hover:bg-blue-700">
            <Plus size={14} /> Add Mapping
          </button>
          <button onClick={handleApply} disabled={applying}
            className="flex items-center gap-1 text-sm bg-green-600 text-white px-3 py-1.5 rounded hover:bg-green-700 disabled:opacity-50">
            <Play size={14} /> {applying ? 'Applying…' : 'Apply All'}
          </button>
          <button onClick={load} className="flex items-center gap-1 text-sm text-gray-600 border border-gray-300 rounded px-2 py-1">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {showForm && (
        <div className="bg-white border border-gray-200 rounded-lg p-4 mb-4 flex gap-3 items-end">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Type</label>
            <select className="border border-gray-300 rounded px-2 py-1 text-sm" value={form.mapping_type}
              onChange={(e) => setForm({ ...form, mapping_type: e.target.value })}>
              {MAPPING_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div className="flex-1">
            <label className="block text-xs text-gray-500 mb-1">Original term</label>
            <input className="border border-gray-300 rounded px-2 py-1 text-sm w-full" value={form.original_term}
              onChange={(e) => setForm({ ...form, original_term: e.target.value })} placeholder="e.g. brie de meaux" />
          </div>
          <div className="flex-1">
            <label className="block text-xs text-gray-500 mb-1">Canonical term</label>
            <input className="border border-gray-300 rounded px-2 py-1 text-sm w-full" value={form.canonical_term}
              onChange={(e) => setForm({ ...form, canonical_term: e.target.value })} placeholder="e.g. soft ripened" />
          </div>
          <button onClick={handleCreate} className="bg-blue-600 text-white text-sm px-3 py-1 rounded hover:bg-blue-700">Save</button>
          <button onClick={() => setShowForm(false)} className="text-sm text-gray-500 px-2 py-1">Cancel</button>
        </div>
      )}

      {loading ? <p className="text-gray-500 text-sm">Loading…</p> : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {['Type', 'Original', 'Canonical', 'Source', 'Applied', ''].map((h) => (
                  <th key={h} className="px-3 py-2 text-left font-medium text-gray-600">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {mappings.map((m) => (
                <tr key={m.id} className="hover:bg-gray-50">
                  <td className="px-3 py-2"><span className="px-2 py-0.5 bg-gray-100 rounded text-xs">{m.mapping_type}</span></td>
                  <td className="px-3 py-2 font-mono text-xs">{m.original_term}</td>
                  <td className="px-3 py-2 font-mono text-xs text-green-700">{m.canonical_term}</td>
                  <td className="px-3 py-2 text-gray-500">{m.source}</td>
                  <td className="px-3 py-2 text-gray-500">{m.applied_count}</td>
                  <td className="px-3 py-2">
                    <button onClick={() => handleDelete(m.id)} className="text-red-400 hover:text-red-600 p-1">
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
              {mappings.length === 0 && (
                <tr><td colSpan={6} className="px-3 py-6 text-center text-gray-400">No mappings yet. Add one to start normalizing terms.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
