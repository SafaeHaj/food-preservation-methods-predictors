import { useState, useRef, useCallback, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import * as XLSX from 'xlsx'
import {
  Upload, Download, ChevronRight, ChevronLeft, Check, X,
  AlertCircle, Info, RefreshCw, Bookmark, Activity,
  HelpCircle, BarChart3, Trash2, Loader2,
} from 'lucide-react'
import clsx from 'clsx'
import {
  ROLES, ROLE_MAP, detectDataType, detectDatasetType, suggestRole,
  getRequiredRoles, getOptionalRoles,
  KINETIC_TEMPLATE_ROWS, SURVIVAL_TEMPLATE_ROWS,
  type ModelFamily, type DataType, type RoleId,
} from '../data/columnRoles'
import {
  uploadDataset, listDatasets, updateMapping as apiUpdateMapping,
  deleteDataset as apiDeleteDataset, downloadDatasetUrl,
  type BackendDataset,
} from '../services/modelLabApi'

// ─── Types ────────────────────────────────────────────────────────────────────
interface ParsedFile {
  name: string
  size: number
  headers: string[]
  rows: string[][]
  totalRows: number
}

type ColumnMapping = Record<string, RoleId>

interface ColumnMeta {
  name: string
  type: DataType
  samples: string[]
  uniqueCount: number
}

// loading = initial fetch from backend
// upload  = no dataset yet (or user clicked Replace)
// mapping = file parsed/restored; user is assigning roles
// ready   = dataset saved with confirmed mapping
type Step = 'loading' | 'upload' | 'mapping' | 'ready'

// ─── LocalStorage template helpers ───────────────────────────────────────────
interface StoredTemplate {
  mapping: ColumnMapping
  family: ModelFamily
  savedAt: string
}
const STORAGE_KEY = (pid: string) => `col_mapping_${pid}`

function loadTemplate(pid: string): StoredTemplate | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY(pid))
    return raw ? (JSON.parse(raw) as StoredTemplate) : null
  } catch { return null }
}

function saveTemplate(pid: string, mapping: ColumnMapping, family: ModelFamily) {
  localStorage.setItem(STORAGE_KEY(pid), JSON.stringify({ mapping, family, savedAt: new Date().toISOString() }))
}

// ─── Parse helpers ────────────────────────────────────────────────────────────
function parseCSVText(text: string): { headers: string[]; rows: string[][] } {
  const lines = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n')
  const nonEmpty = lines.filter((l) => l.trim() !== '')
  if (nonEmpty.length === 0) return { headers: [], rows: [] }

  const parseRow = (line: string): string[] => {
    const result: string[] = []
    let cur = '', inQuote = false
    for (let i = 0; i < line.length; i++) {
      const ch = line[i]
      if (ch === '"') {
        if (inQuote && line[i + 1] === '"') { cur += '"'; i++ }
        else { inQuote = !inQuote }
      } else if (ch === ',' && !inQuote) {
        result.push(cur.trim()); cur = ''
      } else {
        cur += ch
      }
    }
    result.push(cur.trim())
    return result
  }

  const headers = parseRow(nonEmpty[0])
  const rows = nonEmpty.slice(1).map(parseRow)
  return { headers, rows }
}

function parseXLSXBuffer(buf: ArrayBuffer): { headers: string[]; rows: string[][] } {
  const wb = XLSX.read(buf, { type: 'array', cellText: true, raw: false })
  const ws = wb.Sheets[wb.SheetNames[0]]
  const data = XLSX.utils.sheet_to_json<string[]>(ws, { header: 1, defval: '' })
  if (data.length === 0) return { headers: [], rows: [] }
  const headers = (data[0] as unknown[]).map(String)
  const rows = (data.slice(1) as unknown[][]).map((r) => r.map(String))
  return { headers, rows }
}

function buildColumnMeta(headers: string[], rows: string[][]): ColumnMeta[] {
  return headers.map((name, ci) => {
    const colVals = rows.map((r) => r[ci] ?? '').filter((v) => v !== '')
    const type = detectDataType(colVals)
    const unique = Array.from(new Set(colVals))
    return { name, type, samples: unique.slice(0, 4), uniqueCount: unique.length }
  })
}

function buildColumnMetaFromBackend(
  headers: string[],
  columnTypes: Record<string, string>,
): ColumnMeta[] {
  return headers.map((name) => ({
    name,
    type: (columnTypes[name] ?? 'text') as DataType,
    samples: [],
    uniqueCount: 0,
  }))
}

function downloadTemplate(type: 'kinetic' | 'survival') {
  const rows = type === 'kinetic' ? KINETIC_TEMPLATE_ROWS : SURVIVAL_TEMPLATE_ROWS
  const csv = rows.map((r) => r.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = `${type}_template.csv`
  document.body.appendChild(a); a.click()
  document.body.removeChild(a); URL.revokeObjectURL(url)
}

// ─── Sub-components ───────────────────────────────────────────────────────────
const TYPE_STYLES: Record<DataType, { label: string; cls: string }> = {
  numeric:     { label: 'Numeric',  cls: 'bg-blue-50 text-blue-700 border-blue-200' },
  boolean:     { label: '0 / 1',   cls: 'bg-green-50 text-green-700 border-green-200' },
  categorical: { label: 'Category',cls: 'bg-amber-50 text-amber-700 border-amber-200' },
  text:        { label: 'Text',     cls: 'bg-slate-100 text-slate-600 border-slate-200' },
}

function TypeBadge({ type }: { type: DataType }) {
  const s = TYPE_STYLES[type]
  return (
    <span className={clsx('text-[10px] font-bold px-2 py-0.5 rounded-full border', s.cls)}>
      {s.label}
    </span>
  )
}

function RoleSelect({
  value, family, onChange,
}: { value: RoleId; family: ModelFamily; onChange: (r: RoleId) => void }) {
  const familyRoles = ROLES.filter((r) => r.families.includes(family))
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as RoleId)}
      className={clsx(
        'w-full border rounded-lg px-2.5 py-1.5 text-[12px] font-medium',
        'focus:outline-none focus:ring-2 focus:ring-violet-400 focus:border-transparent',
        'transition-colors appearance-none',
        value === 'unassigned'   ? 'border-slate-200 text-slate-400 bg-white'
        : value === 'ignore'     ? 'border-slate-200 text-slate-400 bg-slate-50 italic'
        : ROLE_MAP[value]?.required.includes(family)
          ? 'border-violet-300 text-violet-800 bg-violet-50'
          : 'border-teal-200 text-teal-800 bg-teal-50'
      )}
    >
      <option value="unassigned">— choose role —</option>
      {familyRoles.map((r) => (
        <option key={r.id} value={r.id}>
          {r.label}{r.required.includes(family) ? ' *' : ''}
        </option>
      ))}
      <option value="ignore">Ignore this column</option>
    </select>
  )
}

function MappingStatus({ family, mapping }: { family: ModelFamily; mapping: ColumnMapping }) {
  const required = getRequiredRoles(family)
  const optional = getOptionalRoles(family)
  const assignedRoles = new Set<string>(Object.values(mapping).filter((v) => v !== 'ignore' && v !== 'unassigned'))
  const missingRequired = required.filter((r) => !assignedRoles.has(r))

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden sticky top-4">
      <div className="px-4 py-3 border-b border-slate-100">
        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">Required for training</p>
        <ul className="space-y-1.5">
          {required.map((r) => {
            const ok = assignedRoles.has(r)
            return (
              <li key={r} className="flex items-center gap-2 text-[12px]">
                {ok
                  ? <Check size={12} className="text-green-500 shrink-0" />
                  : <X size={12} className="text-red-400 shrink-0" />}
                <span className={ok ? 'text-slate-700' : 'text-slate-500'}>{ROLE_MAP[r]?.label}</span>
                {ok && (
                  <span className="ml-auto text-[10px] text-slate-400 truncate max-w-[80px]">
                    ← {Object.keys(mapping).find((k) => mapping[k] === r)}
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      </div>
      <div className="px-4 py-3">
        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">Optional</p>
        <ul className="space-y-1.5">
          {optional.map((r) => {
            const ok = assignedRoles.has(r)
            return (
              <li key={r} className="flex items-center gap-2 text-[12px]">
                <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0', ok ? 'bg-violet-400' : 'bg-slate-200')} />
                <span className={ok ? 'text-slate-700' : 'text-slate-400'}>{ROLE_MAP[r]?.label}</span>
              </li>
            )
          })}
        </ul>
      </div>
      {missingRequired.length > 0 && (
        <div className="border-t border-red-100 bg-red-50 px-4 py-3">
          <div className="flex gap-2">
            <AlertCircle size={13} className="text-red-500 shrink-0 mt-0.5" />
            <p className="text-[11px] text-red-700 leading-snug">
              Map <strong>{missingRequired.map((r) => ROLE_MAP[r]?.label).join(', ')}</strong> to enable model training.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function DatasetTab({ onGoToTrain }: { onGoToTrain?: () => void }) {
  const { projectId: projectIdStr = '0' } = useParams<{ projectId: string }>()
  const projectId = parseInt(projectIdStr, 10)

  const [step, setStep] = useState<Step>('loading')
  const [backendDataset, setBackendDataset] = useState<BackendDataset | null>(null)
  const [parsed, setParsed] = useState<ParsedFile | null>(null)
  const [colMeta, setColMeta] = useState<ColumnMeta[]>([])
  const [detectedFamily, setDetectedFamily] = useState<ModelFamily>('kinetic')
  const [detectionConf, setDetectionConf] = useState<'high' | 'medium' | 'low'>('low')
  const [family, setFamily] = useState<ModelFamily>('kinetic')
  const [mapping, setMapping] = useState<ColumnMapping>({})
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [savedTemplate, setSavedTemplate] = useState<StoredTemplate | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // ── Restore from backend on mount ───────────────────────────────────────────
  useEffect(() => {
    if (!projectId) { setStep('upload'); return }
    setSavedTemplate(loadTemplate(String(projectId)))

    listDatasets(projectId)
      .then((datasets) => {
        const active = datasets.find(
          (d) => d.parse_status === 'ready'
        )
        if (!active) { setStep('upload'); return }

        setBackendDataset(active)

        const restoredFamily = (active.dataset_family ?? 'kinetic') as ModelFamily
        setFamily(restoredFamily)

        const restoredMapping: ColumnMapping = {}
        for (const [col, role] of Object.entries(active.column_mapping ?? {})) {
          restoredMapping[col] = role as RoleId
        }
        setMapping(restoredMapping)
        setColMeta(buildColumnMetaFromBackend(active.headers, active.column_types))

        const hasMapping = Object.keys(restoredMapping).length > 0
        setStep(hasMapping ? 'ready' : 'mapping')
      })
      .catch(() => setStep('upload'))
  }, [projectId])

  // ── File ingestion (local parse + backend upload) ───────────────────────────
  const ingestFile = useCallback(async (file: File) => {
    setError(null)
    setUploading(true)
    try {
      // 1. Parse locally for rich mapping UI
      let headers: string[] = []
      let rows: string[][] = []

      if (file.name.toLowerCase().endsWith('.csv') || file.type === 'text/csv') {
        const text = await file.text()
        ;({ headers, rows } = parseCSVText(text))
      } else {
        const buf = await file.arrayBuffer()
        ;({ headers, rows } = parseXLSXBuffer(buf))
      }

      if (headers.length === 0) {
        setError('Could not parse any column headers from this file.')
        setUploading(false)
        return
      }

      const previewRows = rows.slice(0, 500)
      setParsed({ name: file.name, size: file.size, headers, rows: previewRows, totalRows: rows.length })

      const meta = buildColumnMeta(headers, previewRows)
      setColMeta(meta)

      const { type, confidence } = detectDatasetType(headers, previewRows)
      const detFamily: ModelFamily = type === 'unknown' ? 'kinetic' : type
      setDetectedFamily(detFamily)
      setDetectionConf(confidence)
      setFamily(detFamily)

      const autoMapping: ColumnMapping = {}
      for (const col of meta) {
        autoMapping[col.name] = suggestRole(col.name, col.type, col.samples, detFamily)
      }
      const tpl = loadTemplate(String(projectId))
      if (tpl) {
        for (const colName of headers) {
          if (tpl.mapping[colName]) autoMapping[colName] = tpl.mapping[colName]
        }
      }
      setMapping(autoMapping)

      // 2. Upload to backend (replace existing if present)
      const forceReplace = backendDataset != null
      const { dataset } = await uploadDataset(projectId, file, detFamily, forceReplace)
      setBackendDataset(dataset)

      setStep('mapping')
    } catch (e: unknown) {
      setError(`Upload failed: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setUploading(false)
    }
  }, [projectId, backendDataset])

  const handleFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return
    ingestFile(files[0])
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files)
  }

  // ── Mapping helpers ─────────────────────────────────────────────────────────
  const setRole = (col: string, role: RoleId) => {
    setMapping((prev) => {
      const next = { ...prev }
      if (role !== 'ignore' && role !== 'unassigned') {
        for (const k of Object.keys(next)) {
          if (next[k] === role && k !== col) next[k] = 'unassigned'
        }
      }
      next[col] = role
      return next
    })
  }

  const reassignForFamily = (newFamily: ModelFamily) => {
    setFamily(newFamily)
    const newMapping: ColumnMapping = {}
    for (const col of colMeta) {
      const cur = mapping[col.name]
      const curRole = ROLE_MAP[cur ?? '']
      if (cur && cur !== 'ignore' && cur !== 'unassigned' && curRole?.families.includes(newFamily)) {
        newMapping[col.name] = cur
      } else if (cur === 'ignore') {
        newMapping[col.name] = 'ignore'
      } else {
        newMapping[col.name] = suggestRole(col.name, col.type, col.samples, newFamily)
      }
    }
    setMapping(newMapping)
  }

  const handleSaveTemplate = () => {
    saveTemplate(String(projectId), mapping, family)
    setSavedTemplate(loadTemplate(String(projectId)))
  }

  const handleApplyTemplate = () => {
    const tpl = loadTemplate(String(projectId))
    if (!tpl) return
    const merged = { ...mapping }
    const headers = backendDataset?.headers ?? parsed?.headers ?? []
    for (const col of headers) {
      if (tpl.mapping[col]) merged[col] = tpl.mapping[col]
    }
    setFamily(tpl.family)
    setMapping(merged)
  }

  const handleConfirmMapping = async () => {
    if (!backendDataset) return
    setUploading(true)
    setError(null)
    try {
      const updated = await apiUpdateMapping(projectId, backendDataset.id, mapping, family)
      setBackendDataset(updated)
      setStep('ready')
    } catch (e: unknown) {
      setError(`Failed to save mapping: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async () => {
    if (!backendDataset) return
    setDeleting(true)
    try {
      await apiDeleteDataset(projectId, backendDataset.id)
      setBackendDataset(null); setParsed(null); setColMeta([]); setMapping({})
      setStep('upload')
    } catch (e: unknown) {
      setError(`Delete failed: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setDeleting(false)
    }
  }

  const handleReopenMapping = () => {
    if (!backendDataset) return
    const restoredMapping: ColumnMapping = {}
    for (const [col, role] of Object.entries(backendDataset.column_mapping ?? {})) {
      restoredMapping[col] = role as RoleId
    }
    setMapping(restoredMapping)
    setColMeta(buildColumnMetaFromBackend(backendDataset.headers, backendDataset.column_types))
    setFamily((backendDataset.dataset_family ?? 'kinetic') as ModelFamily)
    setStep('mapping')
  }

  const requiredRoles = getRequiredRoles(family)
  const assignedRoles = new Set<string>(Object.values(mapping).filter((v) => v !== 'ignore' && v !== 'unassigned'))
  const allRequiredMapped = requiredRoles.every((r) => assignedRoles.has(r))

  // ─────────────────────────────────────────────────────────────────────────
  // STEP: LOADING
  // ─────────────────────────────────────────────────────────────────────────
  if (step === 'loading') {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="flex flex-col items-center gap-3">
          <Loader2 size={28} className="text-violet-500 animate-spin" />
          <p className="text-sm text-slate-500">Checking for saved dataset…</p>
        </div>
      </div>
    )
  }

  // ─────────────────────────────────────────────────────────────────────────
  // STEP: UPLOAD
  // ─────────────────────────────────────────────────────────────────────────
  if (step === 'upload') {
    return (
      <div className="space-y-7 max-w-3xl">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Training Dataset</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            Upload your data file — you will map your column names in the next step.
            Your column names can be anything.
          </p>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => !uploading && inputRef.current?.click()}
          className={clsx(
            'relative border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all duration-200 select-none',
            uploading
              ? 'border-violet-300 bg-violet-50/60 cursor-wait'
              : dragging
                ? 'border-violet-400 bg-violet-50'
                : 'border-slate-200 bg-slate-50/40 hover:border-violet-300 hover:bg-violet-50/20'
          )}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".csv,.xlsx,.xls"
            className="sr-only"
            onChange={(e) => handleFiles(e.target.files)}
          />
          <div className="w-14 h-14 mx-auto rounded-2xl bg-violet-100 flex items-center justify-center mb-4">
            {uploading
              ? <Loader2 size={24} className="text-violet-600 animate-spin" />
              : <Upload size={24} className="text-violet-600" />}
          </div>
          <p className="font-semibold text-slate-800 text-[15px]">
            {uploading ? 'Uploading…' : 'Drop your data file here'}
          </p>
          {!uploading && (
            <>
              <p className="text-sm text-slate-400 mt-1.5">or click to browse</p>
              <div className="mt-4 flex items-center justify-center gap-3">
                {['CSV', 'XLSX', 'XLS'].map((ext) => (
                  <span key={ext} className="text-[11px] font-bold text-slate-500 bg-slate-100 px-2.5 py-1 rounded-full">
                    .{ext}
                  </span>
                ))}
              </div>
              <p className="mt-4 text-[12px] text-slate-400 flex items-center justify-center gap-1.5">
                <Info size={11} />
                Your column names can be different — you will map them after upload.
              </p>
            </>
          )}
        </div>

        {error && (
          <div className="flex gap-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
            <AlertCircle size={15} className="text-red-500 shrink-0 mt-0.5" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {savedTemplate && (
          <div className="flex items-center gap-3 bg-violet-50 border border-violet-100 rounded-xl px-4 py-3">
            <Bookmark size={14} className="text-violet-500 shrink-0" />
            <p className="text-[12px] text-violet-700 flex-1">
              Saved mapping template for this project ({savedTemplate.family} · saved{' '}
              {new Date(savedTemplate.savedAt).toLocaleDateString()}).
              It will auto-apply when column names match.
            </p>
          </div>
        )}

        {/* Template downloads */}
        <div className="space-y-3">
          <p className="text-[11px] font-bold uppercase tracking-widest text-slate-400">Download example templates</p>
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={(e) => { e.stopPropagation(); downloadTemplate('kinetic') }}
              className="flex items-center gap-3 bg-white border border-slate-200 hover:border-teal-300 hover:bg-teal-50/30 rounded-xl px-4 py-4 text-left transition-all group"
            >
              <div className="w-9 h-9 rounded-lg bg-teal-100 flex items-center justify-center shrink-0">
                <Activity size={16} className="text-teal-600" />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-800 group-hover:text-teal-700">Kinetic template</p>
                <p className="text-[11px] text-slate-400 mt-0.5">time · log_cfu_g · temperature · treatment</p>
              </div>
              <Download size={13} className="ml-auto text-slate-300 group-hover:text-teal-400 shrink-0" />
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); downloadTemplate('survival') }}
              className="flex items-center gap-3 bg-white border border-slate-200 hover:border-violet-300 hover:bg-violet-50/30 rounded-xl px-4 py-4 text-left transition-all group"
            >
              <div className="w-9 h-9 rounded-lg bg-violet-100 flex items-center justify-center shrink-0">
                <BarChart3 size={16} className="text-violet-600" />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-800 group-hover:text-violet-700">Survival / AFT template</p>
                <p className="text-[11px] text-slate-400 mt-0.5">time_days · event · preservative · packaging</p>
              </div>
              <Download size={13} className="ml-auto text-slate-300 group-hover:text-violet-400 shrink-0" />
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ─────────────────────────────────────────────────────────────────────────
  // STEP: MAPPING
  // ─────────────────────────────────────────────────────────────────────────
  if (step === 'mapping') {
    const fileName = backendDataset?.original_name ?? parsed?.name ?? 'dataset'
    const totalRows = backendDataset?.row_count ?? parsed?.totalRows ?? 0
    const columnCount = backendDataset?.col_count ?? parsed?.headers.length ?? 0

    return (
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-2.5 mb-1">
              {!backendDataset && (
                <>
                  <button
                    onClick={() => setStep('upload')}
                    className="flex items-center gap-1 text-slate-400 hover:text-slate-700 text-[12px] transition-colors"
                  >
                    <ChevronLeft size={13} /> Back
                  </button>
                  <span className="text-slate-200">|</span>
                </>
              )}
              <h2 className="text-lg font-bold text-slate-900">Column Mapping</h2>
            </div>
            <p className="text-sm text-slate-500">
              <span className="font-medium text-slate-700">{fileName}</span>
              {' · '}{columnCount} columns · {totalRows.toLocaleString()} rows
            </p>
          </div>

          <div className="flex items-center gap-2">
            {savedTemplate && (
              <button
                onClick={handleApplyTemplate}
                className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium text-violet-700 bg-violet-50 border border-violet-200 rounded-lg hover:bg-violet-100 transition-colors"
              >
                <Bookmark size={12} /> Apply saved template
              </button>
            )}
            <button
              onClick={handleSaveTemplate}
              className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium text-slate-600 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
            >
              <Bookmark size={12} /> Save template
            </button>
          </div>
        </div>

        {/* Dataset type selector */}
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <HelpCircle size={14} className="text-slate-400 shrink-0" />
              <span className="text-sm font-semibold text-slate-700">Model family:</span>
            </div>
            {detectionConf !== 'low' && (
              <span className={clsx(
                'text-[11px] font-bold px-2.5 py-1 rounded-full border',
                detectionConf === 'high'
                  ? 'bg-green-50 text-green-700 border-green-200'
                  : 'bg-amber-50 text-amber-700 border-amber-200'
              )}>
                Auto-detected: {detectedFamily} ({detectionConf} confidence)
              </span>
            )}
            <div className="ml-auto flex rounded-lg border border-slate-200 overflow-hidden">
              {(['kinetic', 'survival'] as ModelFamily[]).map((f) => (
                <button
                  key={f}
                  onClick={() => reassignForFamily(f)}
                  className={clsx(
                    'px-4 py-1.5 text-[12px] font-semibold transition-colors capitalize',
                    family === f
                      ? f === 'kinetic' ? 'bg-teal-600 text-white' : 'bg-violet-600 text-white'
                      : 'bg-white text-slate-600 hover:bg-slate-50'
                  )}
                >
                  {f === 'kinetic' ? 'Kinetic / Growth' : 'Survival / AFT'}
                </button>
              ))}
            </div>
          </div>
        </div>

        {error && (
          <div className="flex gap-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
            <AlertCircle size={15} className="text-red-500 shrink-0 mt-0.5" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {/* Mapping table + status panel */}
        <div className="grid grid-cols-1 xl:grid-cols-[1fr_220px] gap-6 items-start">
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between">
              <p className="text-[11px] font-bold uppercase tracking-widest text-slate-500">
                {colMeta.length} columns detected
              </p>
              <button
                onClick={() => {
                  const reset: ColumnMapping = {}
                  for (const col of colMeta) {
                    reset[col.name] = suggestRole(col.name, col.type, col.samples, family)
                  }
                  setMapping(reset)
                }}
                className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-violet-600 transition-colors"
              >
                <RefreshCw size={11} /> Reset suggestions
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-100">
                    <th className="text-left px-4 py-2.5 text-[11px] font-bold uppercase tracking-wider text-slate-500 w-48">Your column</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-bold uppercase tracking-wider text-slate-500 w-24">Type</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-bold uppercase tracking-wider text-slate-500">Sample values</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-bold uppercase tracking-wider text-slate-500 w-52">Map to role</th>
                  </tr>
                </thead>
                <tbody>
                  {colMeta.map((col) => {
                    const role = mapping[col.name] ?? 'unassigned'
                    const isRequired = role !== 'ignore' && role !== 'unassigned'
                      && ROLE_MAP[role]?.required.includes(family)
                    return (
                      <tr
                        key={col.name}
                        className={clsx(
                          'border-b border-slate-50 last:border-0 transition-colors',
                          role === 'ignore' ? 'bg-slate-50/60 opacity-50'
                          : role === 'unassigned' ? 'bg-white'
                          : isRequired ? 'bg-violet-50/30'
                          : 'bg-teal-50/20'
                        )}
                      >
                        <td className="px-4 py-2.5">
                          <span className="font-mono text-[12px] text-slate-800 font-semibold">{col.name}</span>
                        </td>
                        <td className="px-4 py-2.5"><TypeBadge type={col.type} /></td>
                        <td className="px-4 py-2.5">
                          {col.samples.length > 0
                            ? (
                              <span className="text-[12px] text-slate-500 font-mono">
                                {col.samples.slice(0, 3).join(', ')}
                                {col.uniqueCount > 3 && (
                                  <span className="text-slate-400"> +{col.uniqueCount - 3} more</span>
                                )}
                              </span>
                            )
                            : <span className="text-[11px] text-slate-300 italic">restored</span>
                          }
                        </td>
                        <td className="px-4 py-2.5">
                          <RoleSelect value={role} family={family} onChange={(r) => setRole(col.name, r)} />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <MappingStatus family={family} mapping={mapping} />
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between pt-2">
          <p className="text-[12px] text-slate-400 flex items-center gap-1.5">
            <Info size={12} />
            * = required for model training. Optional roles improve accuracy.
          </p>
          <button
            disabled={!allRequiredMapped || uploading}
            onClick={handleConfirmMapping}
            className={clsx(
              'flex items-center gap-2 px-6 py-2.5 rounded-xl font-semibold text-sm transition-all',
              allRequiredMapped && !uploading
                ? 'bg-violet-600 hover:bg-violet-700 text-white shadow-sm shadow-violet-100'
                : 'bg-slate-100 text-slate-400 cursor-not-allowed'
            )}
          >
            {uploading
              ? <><Loader2 size={14} className="animate-spin" /> Saving…</>
              : <>Confirm mapping <ChevronRight size={15} /></>}
          </button>
        </div>
      </div>
    )
  }

  // ─────────────────────────────────────────────────────────────────────────
  // STEP: READY
  // ─────────────────────────────────────────────────────────────────────────
  if (step === 'ready' && backendDataset) {
    const activeMappings = Object.entries(backendDataset.column_mapping ?? {}).filter(
      ([, r]) => r !== 'ignore' && r !== 'unassigned'
    )
    const ignoredCount = Object.values(backendDataset.column_mapping ?? {}).filter((r) => r === 'ignore').length
    const activeFamily = (backendDataset.dataset_family ?? 'kinetic') as ModelFamily

    return (
      <div className="space-y-6 max-w-2xl">
        {/* Success banner */}
        <div className="flex items-center gap-4 bg-green-50 border border-green-200 rounded-2xl px-6 py-5">
          <div className="w-12 h-12 rounded-xl bg-green-100 flex items-center justify-center shrink-0">
            <Check size={22} className="text-green-600" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-bold text-green-900">Dataset saved</p>
            <p className="text-sm text-green-700 mt-0.5 truncate">
              {backendDataset.original_name} · {backendDataset.row_count.toLocaleString()} rows ·{' '}
              {activeMappings.length} columns mapped
              {ignoredCount > 0 && ` · ${ignoredCount} ignored`}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <a
              href={downloadDatasetUrl(projectId, backendDataset.id)}
              download={backendDataset.original_name}
              className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium text-slate-600 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
            >
              <Download size={12} /> Download
            </a>
          </div>
        </div>

        {error && (
          <div className="flex gap-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
            <AlertCircle size={15} className="text-red-500 shrink-0 mt-0.5" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {/* Mapping summary */}
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100">
            <p className="text-[11px] font-bold uppercase tracking-widest text-slate-500">
              Confirmed column mapping · {activeFamily} models
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  <th className="text-left px-4 py-2.5 text-[11px] font-bold uppercase tracking-wider text-slate-500">Your column</th>
                  <th className="text-left px-4 py-2.5 text-[11px] font-bold uppercase tracking-wider text-slate-500">→ Role</th>
                  <th className="text-left px-4 py-2.5 text-[11px] font-bold uppercase tracking-wider text-slate-500">Required?</th>
                </tr>
              </thead>
              <tbody>
                {activeMappings.map(([col, role], i) => (
                  <tr key={col} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                    <td className="px-4 py-2 font-mono text-[12px] text-slate-700 font-semibold">{col}</td>
                    <td className="px-4 py-2 text-[12px] text-slate-800">{ROLE_MAP[role as RoleId]?.label ?? role}</td>
                    <td className="px-4 py-2">
                      {ROLE_MAP[role as RoleId]?.required.includes(activeFamily) ? (
                        <span className="text-[10px] font-bold text-violet-700 bg-violet-50 border border-violet-200 px-2 py-0.5 rounded-full">Required</span>
                      ) : (
                        <span className="text-[10px] text-slate-400">Optional</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3 flex-wrap">
          <button
            onClick={handleReopenMapping}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-slate-600 border border-slate-200 rounded-xl bg-white hover:bg-slate-50 transition-colors"
          >
            <ChevronLeft size={14} /> Edit mapping
          </button>
          <button
            onClick={handleSaveTemplate}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-violet-700 border border-violet-200 rounded-xl bg-violet-50 hover:bg-violet-100 transition-colors"
          >
            <Bookmark size={14} /> Save as template
          </button>
          <button
            onClick={() => { setParsed(null); setColMeta([]); setStep('upload') }}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-slate-600 border border-slate-200 rounded-xl bg-white hover:bg-slate-50 transition-colors"
          >
            <Upload size={14} /> Replace file
          </button>
          <button
            disabled={deleting}
            onClick={handleDelete}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-red-600 border border-red-200 rounded-xl bg-red-50 hover:bg-red-100 transition-colors disabled:opacity-50"
          >
            {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
            Delete dataset
          </button>
          <div className="flex-1" />
          {onGoToTrain && (
            <button
              onClick={onGoToTrain}
              className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-700 text-white font-semibold text-sm transition-colors shadow-sm shadow-violet-100"
            >
              Go to Train <ChevronRight size={15} />
            </button>
          )}
        </div>
      </div>
    )
  }

  return null
}
