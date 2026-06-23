import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Check, X, Edit3, Save, AlertTriangle, ChevronDown, ChevronUp, Download } from 'lucide-react'
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

  const visibleFields = fields.slice(0, expanded ? fields.length : 5)

  return (
    <div className="card mb-3">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500 font-mono">#{row.id}</span>
          <StatusBadge status={row.status} />
          {row.reviewer_note && (
            <span className="flex items-center gap-1 text-xs text-amber-400">
              <AlertTriangle size={11} /> {row.reviewer_note.slice(0, 60)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {editing ? (
            <>
              <button onClick={handleSave} className="btn-primary text-xs py-1 px-2"><Save size={12} />Save</button>
              <button onClick={() => { setEditing(false); setDraft(row.data) }} className="btn-secondary text-xs py-1 px-2">Cancel</button>
            </>
          ) : (
            <>
              <button onClick={handleApprove} className="text-green-400 hover:text-green-300 p-1" title="Approve"><Check size={15} /></button>
              <button onClick={handleReject} className="text-red-400 hover:text-red-300 p-1" title="Reject"><X size={15} /></button>
              <button onClick={() => setEditing(true)} className="text-blue-400 hover:text-blue-300 p-1" title="Edit"><Edit3 size={14} /></button>
              <button onClick={() => onDelete(row.id)} className="text-slate-600 hover:text-red-400 p-1" title="Delete"><X size={14} /></button>
            </>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-2 text-sm">
        {visibleFields.map((field) => {
          const val = editing ? draft[field.name] : row.data[field.name]
          const prov = row.provenance[field.name]
          return (
            <div key={field.name}>
              <div className="flex items-center gap-1">
                <span className="text-xs text-slate-500">{field.label}</span>
                {field.unit && <span className="text-xs text-slate-600">({field.unit})</span>}
                {prov?.confidence !== undefined && (
                  <span className={`text-xs ml-auto ${prov.confidence >= 0.8 ? 'text-green-500' : prov.confidence >= 0.5 ? 'text-amber-500' : 'text-red-500'}`}>
                    {Math.round(prov.confidence * 100)}%
                  </span>
                )}
              </div>
              {editing ? (
                field.type === 'select' && field.options ? (
                  <select
                    className="input py-1 text-xs"
                    value={String(draft[field.name] ?? '')}
                    onChange={(e) => setDraft((p) => ({ ...p, [field.name]: e.target.value }))}
                  >
                    <option value="">—</option>
                    {field.options.map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : (
                  <input
                    className="input py-1 text-xs"
                    type={field.type === 'number' ? 'number' : 'text'}
                    value={String(draft[field.name] ?? '')}
                    onChange={(e) => setDraft((p) => ({ ...p, [field.name]: field.type === 'number' ? Number(e.target.value) : e.target.value }))}
                  />
                )
              ) : (
                <div className="text-slate-200 truncate font-mono text-xs">
                  {val !== null && val !== undefined ? String(val) : <span className="text-slate-600">—</span>}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {fields.length > 5 && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-3 text-xs text-slate-500 hover:text-slate-300 flex items-center gap-1"
        >
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          {expanded ? 'Show less' : `Show ${fields.length - 5} more fields`}
        </button>
      )}

      {editing && (
        <div className="mt-3 pt-3 border-t border-slate-800">
          <label className="label">Reviewer Note</label>
          <input
            className="input text-xs py-1"
            placeholder="Add note..."
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
      const data = await reviewApi.list(pid, {
        status: filter === 'all' ? undefined : filter,
        limit: 200,
      })
      setRows(data)
      setSelected(new Set())
    } catch { toast.error('Failed to load rows') }
    finally { setLoading(false) }
  }

  useEffect(() => { loadRows() }, [pid, filter])

  const handleUpdate = (id: number, patch: Partial<ExtractedRow>) => {
    setRows((prev) => prev.map((r) => r.id === id ? { ...r, ...patch } : r))
  }

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
    try {
      await reviewApi.bulkStatus(pid, Array.from(selected), 'approved')
      setRows((prev) => prev.map((r) => selected.has(r.id) ? { ...r, status: 'approved' } : r))
      setSelected(new Set())
      toast.success(`${selected.size} rows approved`)
    } catch { toast.error('Failed') }
  }

  const bulkReject = async () => {
    if (!selected.size) return
    try {
      await reviewApi.bulkStatus(pid, Array.from(selected), 'rejected')
      setRows((prev) => prev.map((r) => selected.has(r.id) ? { ...r, status: 'rejected' } : r))
      setSelected(new Set())
      toast.success(`${selected.size} rows rejected`)
    } catch { toast.error('Failed') }
  }

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const selectAll = () => {
    if (selected.size === rows.length) setSelected(new Set())
    else setSelected(new Set(rows.map((r) => r.id)))
  }

  const fields = project?.schema_fields || []

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3 justify-between flex-wrap">
        <div className="flex items-center gap-3">
          <Link to={`/projects/${pid}`} className="text-slate-500 hover:text-slate-300"><ArrowLeft size={18} /></Link>
          <h1 className="text-xl font-bold">Review Rows</h1>
          <span className="text-slate-500 text-sm">{project?.name}</span>
        </div>
        <button onClick={() => exportApi.excel(pid)} className="btn-secondary text-xs">
          <Download size={13} /> Export Excel
        </button>
      </div>

      {/* Filters & bulk */}
      <div className="flex flex-wrap items-center gap-3">
        {(['all', 'pending', 'approved', 'rejected'] as StatusFilter[]).map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`text-sm px-3 py-1.5 rounded-lg transition-colors ${filter === s ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'}`}
          >
            {s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
        {selected.size > 0 && (
          <div className="flex items-center gap-2 ml-auto">
            <span className="text-xs text-slate-400">{selected.size} selected</span>
            <button onClick={bulkApprove} className="btn-primary text-xs py-1 px-2"><Check size={12} />Approve all</button>
            <button onClick={bulkReject} className="btn-danger text-xs py-1 px-2"><X size={12} />Reject all</button>
          </div>
        )}
      </div>

      {loading ? (
        <div className="text-center text-slate-500 py-16">Loading rows...</div>
      ) : rows.length === 0 ? (
        <div className="text-center text-slate-600 py-16">No rows found for this filter.</div>
      ) : (
        <div>
          <div className="flex items-center gap-2 mb-3 text-xs text-slate-500">
            <input type="checkbox" className="accent-blue-500" checked={selected.size === rows.length && rows.length > 0} onChange={selectAll} />
            <span>{rows.length} rows</span>
          </div>
          {rows.map((row) => (
            <div key={row.id} className="flex gap-2">
              <input
                type="checkbox"
                className="mt-5 accent-blue-500 shrink-0"
                checked={selected.has(row.id)}
                onChange={() => toggleSelect(row.id)}
              />
              <div className="flex-1">
                <RowCard row={row} fields={fields} onUpdate={handleUpdate} onDelete={handleDelete} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
