import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft, Check, X, Edit3, Save, AlertTriangle,
  ChevronDown, ChevronUp, Download, CheckCircle2,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { reviewApi, projectsApi, exportApi } from '../services/api'
import { ExtractedRow, Project, SchemaField } from '../types'

type StatusFilter = 'all' | 'pending' | 'approved' | 'rejected'

const StatusBadge = ({ status }: { status: string }) => {
  const cls: Record<string, string> = {
    pending: 'badge-pending',
    approved: 'badge-approved',
    rejected: 'badge-rejected',
    edited: 'badge-edited',
  }
  return <span className={cls[status] || 'badge-pending'}>{status}</span>
}

const ConfidenceDot = ({ value }: { value?: number }) => {
  if (value === undefined) return null
  const color = value >= 0.8 ? 'bg-emerald-400' : value >= 0.5 ? 'bg-amber-400' : 'bg-red-400'
  return (
    <span title={`${Math.round(value * 100)}% confidence`} className={`inline-block w-1.5 h-1.5 rounded-full ${color} shrink-0`} />
  )
}

function RowCard({
  row, fields, onUpdate, onDelete,
}: {
  row: ExtractedRow
  fields: SchemaField[]
  onUpdate: (id: number, patch: Partial<ExtractedRow>) => void
  onDelete: (id: number) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Record<string, unknown>>(row.data)
  const [expanded, setExpanded] = useState(false)
  const [note, setNote] = useState(row.reviewer_note)

  const handleSave = async () => {
    try {
      const updated = await reviewApi.update(row.project_id, row.id, {
        data: draft,
        reviewer_note: note,
        status: 'edited',
      })
      onUpdate(row.id, updated)
      setEditing(false)
      toast.success('Row updated')
    } catch { toast.error('Failed to update') }
  }

  const handleApprove = async () => {
    try {
      const updated = await reviewApi.update(row.project_id, row.id, { status: 'approved' })
      onUpdate(row.id, updated)
    } catch { toast.error('Failed') }
  }

  const handleReject = async () => {
    try {
      const updated = await reviewApi.update(row.project_id, row.id, { status: 'rejected' })
      onUpdate(row.id, updated)
    } catch { toast.error('Failed') }
  }

  const visibleFields = fields.slice(0, expanded ? fields.length : 6)

  return (
    <div className={`bg-white border rounded-xl shadow-sm mb-3 transition-all ${
      row.status === 'approved' ? 'border-emerald-200' :
      row.status === 'rejected' ? 'border-red-200' :
      'border-slate-200'
    }`}>
      {/* Row header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
        <div className="flex items-center gap-2.5">
          <span className="text-xs text-slate-400 font-mono bg-slate-50 border border-slate-200 px-1.5 py-0.5 rounded">
            #{row.id}
          </span>
          <StatusBadge status={row.status} />
          {row.reviewer_note && (
            <span className="flex items-center gap-1 text-xs text-amber-600 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
              <AlertTriangle size={10} /> {row.reviewer_note.slice(0, 55)}{row.reviewer_note.length > 55 ? '…' : ''}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {editing ? (
            <>
              <button onClick={handleSave} className="btn-primary text-xs py-1.5 px-3">
                <Save size={11} /> Save
              </button>
              <button onClick={() => { setEditing(false); setDraft(row.data) }} className="btn-secondary text-xs py-1.5 px-3">
                Cancel
              </button>
            </>
          ) : (
            <>
              <button
                onClick={handleApprove}
                className="p-1.5 text-emerald-500 hover:bg-emerald-50 rounded-lg transition-colors"
                title="Approve"
              >
                <Check size={15} />
              </button>
              <button
                onClick={handleReject}
                className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                title="Reject"
              >
                <X size={15} />
              </button>
              <button
                onClick={() => setEditing(true)}
                className="p-1.5 text-blue-500 hover:bg-blue-50 rounded-lg transition-colors"
                title="Edit"
              >
                <Edit3 size={13} />
              </button>
              <button
                onClick={() => onDelete(row.id)}
                className="p-1.5 text-slate-300 hover:text-red-400 hover:bg-red-50 rounded-lg transition-colors"
                title="Delete"
              >
                <X size={13} />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Fields grid */}
      <div className="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {visibleFields.map((field) => {
          const val = editing ? draft[field.name] : row.data[field.name]
          const prov = row.provenance[field.name]
          return (
            <div key={field.name} className="space-y-1">
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{field.label}</span>
                {field.unit && <span className="text-xs text-slate-400">({field.unit})</span>}
                <ConfidenceDot value={prov?.confidence} />
              </div>
              {editing ? (
                field.type === 'select' && field.options ? (
                  <select
                    className="input py-1.5 text-xs"
                    value={String(draft[field.name] ?? '')}
                    onChange={(e) => setDraft((p) => ({ ...p, [field.name]: e.target.value }))}
                  >
                    <option value="">—</option>
                    {field.options.map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : (
                  <input
                    className="input py-1.5 text-xs"
                    type={field.type === 'number' ? 'number' : 'text'}
                    value={String(draft[field.name] ?? '')}
                    onChange={(e) => setDraft((p) => ({
                      ...p,
                      [field.name]: field.type === 'number' ? Number(e.target.value) : e.target.value,
                    }))}
                  />
                )
              ) : (
                <div className="text-sm text-slate-900 font-medium truncate">
                  {val !== null && val !== undefined
                    ? String(val)
                    : <span className="text-slate-300">—</span>}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Expand / collapse */}
      {fields.length > 6 && (
        <div className="px-4 pb-3">
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1 transition-colors"
          >
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            {expanded ? 'Show fewer fields' : `Show ${fields.length - 6} more fields`}
          </button>
        </div>
      )}

      {/* Reviewer note when editing */}
      {editing && (
        <div className="px-4 pb-4 pt-1 border-t border-slate-100 mt-1">
          <label className="label">Reviewer Note</label>
          <input
            className="input text-xs py-1.5"
            placeholder="Add note…"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </div>
      )}
    </div>
  )
}

export default function Review() {
  const { projectId } = useParams<{ projectId: string }>()
  const pid = Number(projectId)
  const [project, setProject] = useState<Project | null>(null)
  const [rows, setRows] = useState<ExtractedRow[]>([])
  const [filter, setFilter] = useState<StatusFilter>('pending')
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Set<number>>(new Set())

  useEffect(() => {
    projectsApi.get(pid).then(setProject).catch(() => toast.error('Failed to load project'))
  }, [pid])

  const loadRows = async () => {
    setLoading(true)
    try {
      const data = await reviewApi.list(pid, { status: filter === 'all' ? undefined : filter, limit: 200 })
      setRows(data)
      setSelected(new Set())
    } catch { toast.error('Failed to load rows') }
    finally { setLoading(false) }
  }

  useEffect(() => { loadRows() }, [pid, filter])

  const handleUpdate = (id: number, patch: Partial<ExtractedRow>) =>
    setRows((prev) => prev.map((r) => r.id === id ? { ...r, ...patch } : r))

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this row?')) return
    try {
      await reviewApi.delete(pid, id)
      setRows((prev) => prev.filter((r) => r.id !== id))
      toast.success('Row deleted')
    } catch { toast.error('Failed') }
  }

  const bulkApprove = async () => {
    if (!selected.size) return
    await reviewApi.bulkStatus(pid, Array.from(selected), 'approved')
    setRows((prev) => prev.map((r) => selected.has(r.id) ? { ...r, status: 'approved' } : r))
    setSelected(new Set())
    toast.success(`${selected.size} rows approved`)
  }

  const bulkReject = async () => {
    if (!selected.size) return
    await reviewApi.bulkStatus(pid, Array.from(selected), 'rejected')
    setRows((prev) => prev.map((r) => selected.has(r.id) ? { ...r, status: 'rejected' } : r))
    setSelected(new Set())
    toast.success(`${selected.size} rows rejected`)
  }

  const toggleSelect = (id: number) =>
    setSelected((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })

  const selectAll = () =>
    setSelected(selected.size === rows.length ? new Set() : new Set(rows.map((r) => r.id)))

  const fields = project?.schema_fields || []

  const filterCounts = {
    all: null,
    pending: null,
    approved: null,
    rejected: null,
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3 justify-between flex-wrap">
        <div className="flex items-center gap-3">
          <Link to={`/projects/${pid}`} className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors">
            <ArrowLeft size={18} />
          </Link>
          <div>
            <h1 className="page-title">Review Extractions</h1>
            <p className="muted">{project?.name}</p>
          </div>
        </div>
        <button onClick={() => exportApi.excel(pid)} className="btn-secondary">
          <Download size={14} /> Export Excel
        </button>
      </div>

      {/* Filters bar */}
      <div className="flex flex-wrap items-center gap-2">
        {(['all', 'pending', 'approved', 'rejected'] as StatusFilter[]).map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`text-sm px-4 py-1.5 rounded-lg font-medium transition-all ${
              filter === s
                ? 'bg-blue-600 text-white shadow-sm'
                : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'
            }`}
          >
            {s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}

        {selected.size > 0 && (
          <div className="flex items-center gap-2 ml-auto bg-blue-50 border border-blue-200 rounded-lg px-3 py-1.5">
            <span className="text-xs font-semibold text-blue-700">{selected.size} selected</span>
            <button onClick={bulkApprove} className="btn-primary text-xs py-1 px-2.5 gap-1">
              <Check size={11} /> Approve
            </button>
            <button onClick={bulkReject} className="btn-danger text-xs py-1 px-2.5 gap-1">
              <X size={11} /> Reject
            </button>
          </div>
        )}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : rows.length === 0 ? (
        <div className="text-center py-20">
          <CheckCircle2 size={36} className="text-slate-200 mx-auto mb-3" />
          <p className="text-slate-500 text-sm">No rows found for this filter.</p>
        </div>
      ) : (
        <div>
          <div className="flex items-center gap-2.5 mb-4 text-xs text-slate-500">
            <input
              type="checkbox"
              className="w-3.5 h-3.5 accent-blue-600 rounded"
              checked={selected.size === rows.length && rows.length > 0}
              onChange={selectAll}
            />
            <span>{rows.length} rows</span>
          </div>
          {rows.map((row) => (
            <div key={row.id} className="flex gap-3 items-start">
              <input
                type="checkbox"
                className="mt-4 w-3.5 h-3.5 accent-blue-600 rounded shrink-0"
                checked={selected.has(row.id)}
                onChange={() => toggleSelect(row.id)}
              />
              <div className="flex-1 min-w-0">
                <RowCard row={row} fields={fields} onUpdate={handleUpdate} onDelete={handleDelete} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
