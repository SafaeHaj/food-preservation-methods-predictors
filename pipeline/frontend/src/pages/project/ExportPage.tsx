import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { snapshotsApi } from '../../services/api'
import type { ExportRun } from '../../types'
import { Download, RefreshCw, FileSpreadsheet, Archive, Braces, Database } from 'lucide-react'
import toast from 'react-hot-toast'

const FORMAT_ICONS: Record<string, React.ReactNode> = {
  excel: <FileSpreadsheet size={20} />,
  csv_zip: <Archive size={20} />,
  json: <Braces size={20} />,
  parquet: <Database size={20} />,
}

const STATUS_COLORS: Record<string, string> = {
  completed: 'text-green-700',
  failed: 'text-red-700',
  pending: 'text-gray-500',
  building: 'text-blue-700',
}

export default function ExportPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [runs, setRuns] = useState<ExportRun[]>([])
  const [loading, setLoading] = useState(false)
  const [requesting, setRequesting] = useState(false)

  const loadRuns = async () => {
    // We don't have a list endpoint for exports directly; use snapshot exports
    // This page will show pending/completed exports from the ExportRun model
  }

  const handleExport = async (format: string) => {
    if (!projectId) return
    setRequesting(true)
    try {
      const run = await snapshotsApi.requestExport({
        project_id: Number(projectId),
        format,
      })
      toast.success(`Export started (Run #${run.id})`)
      // Poll until done
      const poll = setInterval(async () => {
        const updated = await snapshotsApi.getExportRun(run.id)
        setRuns((prev) => {
          const idx = prev.findIndex((r) => r.id === run.id)
          if (idx >= 0) { const next = [...prev]; next[idx] = updated; return next }
          return [updated, ...prev]
        })
        if (updated.status === 'completed' || updated.status === 'failed') {
          clearInterval(poll)
          if (updated.status === 'completed') {
            toast.success('Export ready for download')
          } else {
            toast.error(`Export failed: ${updated.error_message}`)
          }
        }
      }, 2000)
    } catch {
      toast.error('Failed to start export')
    } finally {
      setRequesting(false)
    }
  }

  const handleDownload = (runId: number) => {
    snapshotsApi.downloadExport(runId).catch(() => toast.error('Download failed'))
  }

  const formats: { key: string; label: string; desc: string }[] = [
    { key: 'excel', label: 'Excel Workbook', desc: 'Multi-sheet .xlsx with all entities' },
    { key: 'csv_zip', label: 'CSV Archive', desc: 'ZIP of one CSV per table' },
    { key: 'json', label: 'JSON', desc: 'Single JSON with all tables' },
    { key: 'parquet', label: 'Parquet ZIP', desc: 'Columnar format for ML / pandas' },
  ]

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Export Dataset</h1>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-8">
        {formats.map(({ key, label, desc }) => (
          <button
            key={key}
            onClick={() => handleExport(key)}
            disabled={requesting}
            className="bg-white border border-gray-200 rounded-lg p-4 text-left hover:border-blue-400 hover:shadow-sm transition-all disabled:opacity-50 flex items-start gap-3"
          >
            <span className="text-blue-600 mt-0.5">{FORMAT_ICONS[key]}</span>
            <div>
              <p className="font-medium text-gray-900">{label}</p>
              <p className="text-sm text-gray-500 mt-0.5">{desc}</p>
            </div>
          </button>
        ))}
      </div>

      {runs.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-gray-700 mb-2">Recent exports</h2>
          <div className="space-y-2">
            {runs.map((run) => (
              <div key={run.id} className="bg-white border border-gray-200 rounded-lg p-3 flex items-center gap-3">
                <span className="text-gray-500">{FORMAT_ICONS[run.format]}</span>
                <div className="flex-1">
                  <span className={`text-sm font-medium ${STATUS_COLORS[run.status] ?? 'text-gray-700'}`}>
                    {run.status}
                  </span>
                  <span className="text-xs text-gray-400 ml-2">{run.format}</span>
                  {run.file_size_bytes && (
                    <span className="text-xs text-gray-400 ml-2">
                      {(run.file_size_bytes / 1024).toFixed(0)} KB
                    </span>
                  )}
                </div>
                {run.status === 'completed' && (
                  <button onClick={() => handleDownload(run.id)} className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800">
                    <Download size={14} /> Download
                  </button>
                )}
                {run.status === 'building' && (
                  <span className="text-xs text-blue-600 animate-pulse">Building…</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
