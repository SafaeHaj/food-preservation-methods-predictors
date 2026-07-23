import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { studiesApi, projectsApi } from '../../services/api'
import type { Study } from '../../types'
import { CheckCircle, AlertCircle, RefreshCw, Plus, X, Trash2, Zap } from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'

const STATUS_COLORS: Record<string, string> = {
  approved: 'text-green-700 bg-green-50',
  rejected: 'text-red-700 bg-red-50',
  extracted: 'text-gray-700 bg-gray-100',
  needs_review: 'text-yellow-700 bg-yellow-50',
  in_review: 'text-blue-700 bg-blue-50',
  changes_requested: 'text-orange-700 bg-orange-50',
}

interface StudyForm {
  title: string
  authors: string
  publication_year: string
  journal: string
  doi_original: string
  study_type: string
}

const EMPTY_FORM: StudyForm = { title: '', authors: '', publication_year: '', journal: '', doi_original: '', study_type: '' }

export default function StudiesPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [studies, setStudies] = useState<Study[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<StudyForm>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [syncing, setSyncing] = useState(false)

  const load = () => {
    if (!projectId) return
    setLoading(true)
    setError(null)
    studiesApi
      .list(Number(projectId), statusFilter ? { review_status: statusFilter } : undefined)
      .then(setStudies)
      .catch((e) => setError(e?.response?.data?.detail ?? 'Failed to load studies'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [projectId, statusFilter])

  const handleCreate = async () => {
    if (!projectId || !form.title.trim()) { toast.error('Title is required'); return }
    setSaving(true)
    try {
      await studiesApi.create({
        project_id: Number(projectId),
        title: form.title.trim(),
        authors: form.authors.split(',').map((a) => a.trim()).filter(Boolean),
        publication_year: form.publication_year ? Number(form.publication_year) : undefined,
        journal: form.journal.trim() || undefined,
        doi_original: form.doi_original.trim() || undefined,
        study_type: form.study_type || undefined,
        review_status: 'extracted',
      })
      toast.success('Study created')
      setShowForm(false)
      setForm(EMPTY_FORM)
      load()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to create study'
      toast.error(msg)
    } finally {
      setSaving(false)
    }
  }

  const handleApprove = async (id: number) => {
    try {
      await studiesApi.approve(id)
      toast.success('Study approved')
      load()
    } catch { toast.error('Failed to approve') }
  }

  const handleReject = async (id: number) => {
    const reason = window.prompt('Reason for rejection (optional):')
    try {
      await studiesApi.reject(id, reason ?? undefined)
      toast.success('Study rejected')
      load()
    } catch { toast.error('Failed to reject') }
  }

  const handleDelete = async (id: number, title: string) => {
    if (!confirm(`Delete "${title}"?`)) return
    try {
      await studiesApi.delete(id)
      toast.success('Deleted')
      load()
    } catch { toast.error('Failed to delete') }
  }

  const handleSync = async () => {
    if (!projectId) return
    setSyncing(true)
    try {
      const result = await projectsApi.promoteCanonical(Number(projectId))
      toast.success(`Synced: ${result.studies} studies, ${result.experiments} experiments, ${result.observations} observations`)
      load()
    } catch {
      toast.error('Sync failed')
    } finally {
      setSyncing(false)
    }
  }

  const set = (k: keyof StudyForm) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Studies</h1>
        <div className="flex gap-2">
          <select
            className="border border-gray-300 rounded px-2 py-1 text-sm"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All statuses</option>
            <option value="extracted">Extracted</option>
            <option value="needs_review">Needs review</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="flex items-center gap-1 text-sm text-emerald-700 bg-emerald-50 border border-emerald-300 px-3 py-1.5 rounded hover:bg-emerald-100 disabled:opacity-50"
            title="Promote all extracted PDF rows to studies/experiments/observations"
          >
            <Zap size={14} /> {syncing ? 'Syncing…' : 'Sync from PDFs'}
          </button>
          <button
            onClick={() => setShowForm((v) => !v)}
            className="flex items-center gap-1 text-sm bg-blue-600 text-white px-3 py-1.5 rounded hover:bg-blue-700"
          >
            <Plus size={14} /> New Study
          </button>
          <button onClick={load} className="flex items-center gap-1 text-sm text-gray-600 border border-gray-300 rounded px-2 py-1">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {showForm && (
        <div className="bg-white border border-blue-200 rounded-lg p-4 mb-4 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-medium text-gray-900">New Study</h2>
            <button onClick={() => { setShowForm(false); setForm(EMPTY_FORM) }} className="text-gray-400 hover:text-gray-600">
              <X size={16} />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="block text-xs text-gray-500 mb-1">Title *</label>
              <input
                className="border border-gray-300 rounded px-2 py-1.5 text-sm w-full"
                placeholder="e.g. Effect of NaCl on Listeria monocytogenes in soft cheese"
                value={form.title}
                onChange={set('title')}
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Authors (comma-separated)</label>
              <input
                className="border border-gray-300 rounded px-2 py-1.5 text-sm w-full"
                placeholder="Smith J, Doe A"
                value={form.authors}
                onChange={set('authors')}
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Year</label>
              <input
                type="number"
                className="border border-gray-300 rounded px-2 py-1.5 text-sm w-full"
                placeholder="2023"
                value={form.publication_year}
                onChange={set('publication_year')}
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Journal</label>
              <input
                className="border border-gray-300 rounded px-2 py-1.5 text-sm w-full"
                placeholder="Food Microbiology"
                value={form.journal}
                onChange={set('journal')}
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">DOI</label>
              <input
                className="border border-gray-300 rounded px-2 py-1.5 text-sm w-full"
                placeholder="10.1016/..."
                value={form.doi_original}
                onChange={set('doi_original')}
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Study type</label>
              <select className="border border-gray-300 rounded px-2 py-1.5 text-sm w-full" value={form.study_type} onChange={set('study_type')}>
                <option value="">— select —</option>
                <option value="challenge_study">Challenge study</option>
                <option value="growth_study">Growth study</option>
                <option value="inactivation_study">Inactivation study</option>
                <option value="shelf_life">Shelf-life study</option>
                <option value="survey">Survey</option>
                <option value="review">Review</option>
                <option value="other">Other</option>
              </select>
            </div>
          </div>
          <div className="flex gap-2 mt-4">
            <button
              onClick={handleCreate}
              disabled={saving}
              className="bg-blue-600 text-white text-sm px-4 py-1.5 rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? 'Creating…' : 'Create Study'}
            </button>
            <button onClick={() => { setShowForm(false); setForm(EMPTY_FORM) }} className="text-sm text-gray-500 px-3 py-1.5 border border-gray-300 rounded hover:bg-gray-50">
              Cancel
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700 flex items-center gap-2">
          <AlertCircle size={14} />
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-gray-500 text-sm">Loading studies…</p>
      ) : studies.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <p className="text-lg font-medium">No studies yet</p>
          <p className="text-sm mt-1 mb-4">If you've already extracted PDFs, click <strong>Sync from PDFs</strong> to promote the data here.</p>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="inline-flex items-center gap-1.5 text-sm text-emerald-700 bg-emerald-50 border border-emerald-300 px-4 py-2 rounded-lg hover:bg-emerald-100 disabled:opacity-50"
          >
            <Zap size={15} /> {syncing ? 'Syncing…' : 'Sync from PDFs'}
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          {studies.map((s) => (
            <div key={s.id} className="bg-white border border-gray-200 rounded-lg p-4 flex items-start gap-4 group">
              <div className="flex-1 min-w-0">
                <p className="font-medium text-gray-900 truncate">{s.title ?? `Study #${s.id}`}</p>
                <p className="text-sm text-gray-500 mt-0.5">
                  {(s.authors ?? []).slice(0, 3).join(', ')}{(s.authors ?? []).length > 3 ? ` +${(s.authors ?? []).length - 3}` : ''}
                  {s.publication_year ? ` · ${s.publication_year}` : ''}
                  {s.journal ? ` · ${s.journal}` : ''}
                  {s.study_type ? ` · ${s.study_type}` : ''}
                </p>
                {s.doi_normalized && <p className="text-xs text-gray-400 mt-0.5">{s.doi_normalized}</p>}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className={clsx('px-2 py-0.5 rounded text-xs font-medium', STATUS_COLORS[s.review_status] ?? 'bg-gray-100 text-gray-700')}>
                  {s.review_status.replace(/_/g, ' ')}
                </span>
                {s.review_status !== 'approved' && (
                  <button onClick={() => handleApprove(s.id)} className="text-green-600 hover:text-green-800 p-1" title="Approve">
                    <CheckCircle size={16} />
                  </button>
                )}
                {s.review_status !== 'rejected' && (
                  <button onClick={() => handleReject(s.id)} className="text-orange-500 hover:text-orange-700 p-1" title="Reject">
                    <AlertCircle size={16} />
                  </button>
                )}
                <button onClick={() => handleDelete(s.id, s.title ?? `Study #${s.id}`)} className="text-red-400 hover:text-red-600 p-1 opacity-0 group-hover:opacity-100 transition-opacity" title="Delete">
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
