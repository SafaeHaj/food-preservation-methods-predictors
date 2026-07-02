import { useState, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Plus, Trash2, Upload, Save, Info } from 'lucide-react'
import toast from 'react-hot-toast'
import { projectsApi, schemaApi } from '../services/api'
import { SchemaField, Project } from '../types'

const FIELD_TYPES = ['text', 'number', 'select', 'boolean'] as const

const emptyField = (): SchemaField => ({
  name: '',
  label: '',
  type: 'text',
  unit: '',
  required: false,
})

export default function SchemaPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const pid = Number(projectId)
  const [project, setProject] = useState<Project | null>(null)
  const [fields, setFields] = useState<SchemaField[]>([])
  const [saving, setSaving] = useState(false)
  const [inferring, setInferring] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    projectsApi.get(pid).then((p) => {
      setProject(p)
      setFields(p.schema_fields)
    }).catch(() => toast.error('Failed to load project'))
  }, [pid])

  const update = (i: number, patch: Partial<SchemaField>) =>
    setFields((prev) => prev.map((f, idx) => idx === i ? { ...f, ...patch } : f))

  const add = () => setFields((prev) => [...prev, emptyField()])
  const remove = (i: number) => setFields((prev) => prev.filter((_, idx) => idx !== i))

  const handleSave = async () => {
    const invalid = fields.filter((f) => !f.name.trim() || !f.label.trim())
    if (invalid.length) { toast.error('All fields need a name and label'); return }
    setSaving(true)
    try {
      await projectsApi.update(pid, { schema_fields: fields })
      toast.success('Schema saved successfully')
    } catch {
      toast.error('Failed to save schema')
    } finally {
      setSaving(false)
    }
  }

  const handleInferFromExcel = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setInferring(true)
    try {
      const inferred: SchemaField[] = await schemaApi.infer(file)
      setFields(inferred)
      toast.success(`${inferred.length} fields inferred from Excel`)
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to infer schema')
    } finally {
      setInferring(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3 justify-between flex-wrap">
        <div className="flex items-center gap-3">
          <Link to={`/projects/${pid}`} className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors">
            <ArrowLeft size={18} />
          </Link>
          <div>
            <h1 className="page-title">Schema Editor</h1>
            <p className="muted">{project?.name}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xls"
            className="hidden"
            onChange={handleInferFromExcel}
          />
          <button onClick={() => fileRef.current?.click()} className="btn-secondary" disabled={inferring}>
            <Upload size={14} />
            {inferring ? 'Inferring…' : 'Infer from Excel'}
          </button>
          <button onClick={add} className="btn-secondary">
            <Plus size={14} /> Add Field
          </button>
          <button onClick={handleSave} className="btn-primary" disabled={saving}>
            <Save size={14} />
            {saving ? 'Saving…' : 'Save Schema'}
          </button>
        </div>
      </div>

      {/* Info banner */}
      <div className="flex items-start gap-3 bg-blue-50 border border-blue-200 rounded-xl p-4">
        <Info size={15} className="text-blue-500 mt-0.5 shrink-0" />
        <p className="text-sm text-blue-700">
          Define the fields you want the AI to extract from each paper.
          <strong> field_name</strong> must be snake_case and unique. Label is shown in the UI.
          Validation ranges are enforced during review.
        </p>
      </div>

      {/* Schema table */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        {/* Column headers */}
        <div className="px-5 py-3 border-b border-slate-100 bg-slate-50 grid grid-cols-12 gap-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">
          <span className="col-span-3">Field Name</span>
          <span className="col-span-3">Display Label</span>
          <span className="col-span-2">Type</span>
          <span className="col-span-2">Unit</span>
          <span className="col-span-1 text-center">Required</span>
          <span className="col-span-1" />
        </div>

        {fields.length === 0 ? (
          <div className="text-center py-14">
            <div className="w-10 h-10 bg-slate-100 rounded-xl flex items-center justify-center mx-auto mb-3">
              <Plus size={18} className="text-slate-400" />
            </div>
            <p className="text-sm text-slate-500 mb-4">No fields defined yet</p>
            <div className="flex items-center justify-center gap-2">
              <button onClick={add} className="btn-primary text-xs">
                <Plus size={13} /> Add Field
              </button>
              <button onClick={() => fileRef.current?.click()} className="btn-secondary text-xs">
                <Upload size={13} /> Infer from Excel
              </button>
            </div>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {fields.map((field, i) => (
              <div key={i} className="px-5 py-3 grid grid-cols-12 gap-3 items-center hover:bg-slate-50 transition-colors group">
                <input
                  className="input col-span-3 py-1.5 font-mono text-xs"
                  placeholder="field_name"
                  value={field.name}
                  onChange={(e) => update(i, { name: e.target.value.toLowerCase().replace(/\s+/g, '_') })}
                />
                <input
                  className="input col-span-3 py-1.5 text-xs"
                  placeholder="Human Readable Label"
                  value={field.label}
                  onChange={(e) => update(i, { label: e.target.value })}
                />
                <select
                  className="input col-span-2 py-1.5 text-xs"
                  value={field.type}
                  onChange={(e) => update(i, { type: e.target.value as SchemaField['type'] })}
                >
                  {FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
                <input
                  className="input col-span-2 py-1.5 text-xs"
                  placeholder="g/100g, pH…"
                  value={field.unit || ''}
                  onChange={(e) => update(i, { unit: e.target.value })}
                />
                <div className="col-span-1 flex justify-center">
                  <input
                    type="checkbox"
                    className="w-4 h-4 accent-blue-600 rounded"
                    checked={field.required || false}
                    onChange={(e) => update(i, { required: e.target.checked })}
                  />
                </div>
                <div className="col-span-1 flex justify-end">
                  <button
                    onClick={() => remove(i)}
                    className="p-1.5 text-slate-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {fields.length > 0 && (
          <div className="px-5 py-3 border-t border-slate-100 bg-slate-50 flex items-center justify-between">
            <p className="text-xs text-slate-500">
              {fields.length} field{fields.length !== 1 ? 's' : ''} · For <code className="text-xs bg-slate-200 px-1 py-0.5 rounded">select</code> fields, options are populated automatically during AI extraction
            </p>
            <button onClick={add} className="btn-ghost text-xs text-blue-600 hover:bg-blue-50">
              <Plus size={12} /> Add field
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
