import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useExportRun, useRequestExport } from '../../api/canonical'
import { download } from '../../api/client'
import { errorMessage } from '../../api/errors'
import type { ExportRun } from '../../types'
import { Download, FileSpreadsheet, Archive, Braces, Database } from 'lucide-react'
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
  const [activeRunId, setActiveRunId] = useState<number | null>(null)
  const [requesting, setRequesting] = useState(false)

  const requestExport = useRequestExport(Number(projectId))

  // One query watches the run in flight. Its refetch interval stops itself the moment the
  // run reaches a terminal state, so there is no interval to clear and none can be leaked
  // by navigating away mid-export.
  const { data: activeRun } = useExportRun(activeRunId)

  useEffect(() => {
    if (!activeRun) return
    setRuns((previous) => {
      const index = previous.findIndex((run) => run.id === activeRun.id)
      if (index < 0) return [activeRun as ExportRun, ...previous]
      const next = [...previous]
      next[index] = activeRun as ExportRun
      return next
    })
    if (activeRun.status === 'completed') {
      toast.success('Export ready for download')
      setActiveRunId(null)
    } else if (activeRun.status === 'failed') {
      toast.error('The export failed')
      setActiveRunId(null)
    }
  }, [activeRun])

  const handleExport = async (format: string) => {
    setRequesting(true)
    try {
      const run = await requestExport.mutateAsync({ format })
      toast.success(`Export started (run #${run.id})`)
      setActiveRunId(run.id)
    } catch (error) {
      toast.error(errorMessage(error, 'Could not start the export'))
    } finally {
      setRequesting(false)
    }
  }

  const handleDownload = (runId: number) =>
    download(`/snapshots/exports/${runId}/download`, `export_${runId}`).catch((error) =>
      toast.error(errorMessage(error, 'Download failed')),
    )

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
