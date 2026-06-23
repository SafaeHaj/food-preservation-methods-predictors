import { useState, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Plus, Trash2, Upload, Save } from 'lucide-react'
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

  const update = (i: number, patch: Partial<SchemaField>) => {
    setFields((prev) => prev.map((f, idx) => idx === i ? { ...f, ...patch } : f))
  }

  const add = () => setFields((prev) => [...prev, emptyField()])
  const remove = (i: number) => setFields((prev) => prev.filter((_, idx) => idx !== i))

  const handleSave = async () => {
    const invalid = fields.filter((f) => !f.name.trim() || !f.label.trim())
    if (invalid.length) { toast.error('All fields need a name and label'); return }
    setSaving(true)
    try {
      await projectsApi.update(pid, { schema_fields: fields })
      toast.success('Schema saved')
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
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-3 justify-between flex-wrap">
        <div className="flex items-center gap-3">
          <Link to={`/projects/${pid}`} className="text-slate-500 hover:text-slate-300">
            <ArrowLeft size={18} />
          </Link>
          <div>
            <h1 className="text-xl font-bold">Schema Editor</h1>
            <p className="text-slate-500 text-sm">{project?.name}</p>
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
          <button
            onClick={() => fileRef.current?.click()}
            className="btn-secondary"
            disabled={inferring}
          >
            <Upload size={15} />
            {inferring ? 'Inferring...' : 'Infer from Excel'}
          </button>
          <button onClick={add} className="btn-secondary">
            <Plus size={15} /> Add Field
          </button>
          <button onClick={handleSave} className="btn-primary" disabled={saving}>
            <Save size={15} />
            {saving ? 'Saving...' : 'Save Schema'}
          </button>
        </div>
      </div>

      <div className="card p-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-800 grid grid-cols-12 gap-3 text-xs font-medium text-slate-500 uppercase tracking-wide">
          <span className="col-span-3">Field Name</span>
          <span className="col-span-3">Label</span>
          <span className="col-span-2">Type</span>
          <span className="col-span-2">Unit</span>
          <span className="col-span-1 text-center">Req.</span>
          <span className="col-span-1"></span>
        </div>

        {fields.length === 0 ? (
          <div className="text-center py-12 text-slate-500 text-sm">
            No fields. Add one or infer from an Excel file.
          </div>
        ) : (
          <div className="divide-y divide-slate-800/60">
            {fields.map((field, i) => (
              <div key={i} className="px-5 py-2.5 grid grid-cols-12 gap-3 items-center">
                <input
                  className="input col-span-3 py-1.5 font-mono text-xs"
                  placeholder="field_name"
                  value={field.name}
                  onChange={(e) => update(i, { name: e.target.value.toLowerCase().replace(/\s+/g, '_') })}
                />
                <input
                  className="input col-span-3 py-1.5 text-xs"
                  placeholder="Human Label"
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
                  placeholder="e.g. g/100g"
                  value={field.unit || ''}
                  onChange={(e) => update(i, { unit: e.target.value })}
                />
                <div className="col-span-1 flex justify-center">
                  <input
                    type="checkbox"
                    className="w-4 h-4 accent-blue-500"
                    checked={field.required || false}
                    onChange={(e) => update(i, { required: e.target.checked })}
                  />
                </div>
                <div className="col-span-1 flex justify-end">
                  <button onClick={() => remove(i)} className="text-slate-600 hover:text-red-400">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <p className="text-xs text-slate-600">
        {fields.length} field{fields.length !== 1 ? 's' : ''} defined.
        For select fields, options are set automatically during extraction.
        Validation ranges (min/max) are applied during AI extraction and review.
      </p>
    </div>
  )
}
