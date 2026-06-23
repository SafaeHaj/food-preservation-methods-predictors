import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { Upload, Settings, Eye, BarChart2, Download, RefreshCw, FileText, CheckCircle, XCircle, Clock, Zap } from 'lucide-react'
import toast from 'react-hot-toast'
import { projectsApi, papersApi, extractionApi } from '../services/api'
import { Project, Paper } from '../types'
import { exportApi } from '../services/api'

const StatusBadge = ({ status }: { status: Paper['status'] }) => {
  const map: Record<string, string> = {
    uploaded: 'badge-pending',
    extracting: 'badge-edited',
    extracted: 'badge-extracted',
    reviewed: 'badge-approved',
    error: 'badge-error',
  }
  return <span className={map[status] || 'badge-pending'}>{status}</span>
}

export default function ProjectView() {
  const { projectId } = useParams<{ projectId: string }>()
  const pid = Number(projectId)

  const [project, setProject] = useState<Project | null>(null)
  const [papers, setPapers] = useState<Paper[]>([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const [proj, paps] = await Promise.all([projectsApi.get(pid), papersApi.list(pid)])
      setProject(proj)
      setPapers(paps)
    } catch {
      toast.error('Failed to load project')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const interval = setInterval(() => {
      // Refresh if any paper is extracting
      setPapers((prev) => {
        if (prev.some((p) => p.status === 'extracting')) { load(); }
        return prev
      })
    }, 5000)
    return () => clearInterval(interval)
  }, [pid])

  const handleExtractAll = async () => {
    try {
      await extractionApi.extractAll(pid)
      toast.success('AI extraction started for all pending papers')
      setTimeout(load, 2000)
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Extraction failed')
    }
  }

  const handleExtractOne = async (paperId: number) => {
    try {
      await extractionApi.extractOne(pid, paperId)
      toast.success('AI extraction started')
      setTimeout(load, 2000)
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Extraction failed')
    }
  }

  const handleDelete = async (paperId: number, name: string) => {
    if (!confirm(`Delete "${name}"?`)) return
    try {
      await papersApi.delete(pid, paperId)
      setPapers((prev) => prev.filter((p) => p.id !== paperId))
      toast.success('Paper deleted')
    } catch {
      toast.error('Failed to delete paper')
    }
  }

  const handleExport = async () => {
    try {
      await exportApi.excel(pid)
      toast.success('Excel exported')
    } catch {
      toast.error('Export failed')
    }
  }

  if (loading) return <div className="text-center text-slate-500 py-20">Loading...</div>
  if (!project) return <div className="text-center text-red-400 py-20">Project not found</div>

  const pending = papers.filter((p) => p.status === 'uploaded' || p.status === 'error')

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start gap-4 justify-between">
        <div>
          <div className="text-sm text-slate-500 mb-1">
            <Link to="/" className="hover:text-slate-300">Projects</Link> / {project.name}
          </div>
          <h1 className="text-2xl font-bold text-slate-100">{project.name}</h1>
          {project.description && <p className="text-slate-400 text-sm mt-0.5">{project.description}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to={`/projects/${pid}/upload`} className="btn-primary"><Upload size={15} />Upload PDFs</Link>
          <Link to={`/projects/${pid}/schema`} className="btn-secondary"><Settings size={15} />Schema</Link>
          <Link to={`/projects/${pid}/review`} className="btn-secondary"><Eye size={15} />Review</Link>
          <Link to={`/projects/${pid}/analytics`} className="btn-secondary"><BarChart2 size={15} />Analytics</Link>
          <button onClick={handleExport} className="btn-secondary"><Download size={15} />Export Excel</button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Papers', value: papers.length, icon: FileText },
          { label: 'Extracted', value: papers.filter(p => p.status === 'extracted' || p.status === 'reviewed').length, icon: CheckCircle },
          { label: 'Errors', value: papers.filter(p => p.status === 'error').length, icon: XCircle },
          { label: 'Pending', value: pending.length, icon: Clock },
        ].map(({ label, value, icon: Icon }) => (
          <div key={label} className="card flex items-center gap-3">
            <Icon size={20} className="text-blue-400 shrink-0" />
            <div>
              <div className="text-xl font-bold">{value}</div>
              <div className="text-xs text-slate-500">{label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Papers table */}
      <div className="card p-0 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <h2 className="font-semibold">Papers</h2>
          {pending.length > 0 && (
            <button onClick={handleExtractAll} className="btn-primary text-xs py-1.5">
              <Zap size={13} />
              Extract All ({pending.length})
            </button>
          )}
        </div>
        {papers.length === 0 ? (
          <div className="text-center py-12 text-slate-500">
            No papers yet.{' '}
            <Link to={`/projects/${pid}/upload`} className="text-blue-400 hover:underline">Upload PDFs</Link>
          </div>
        ) : (
          <div className="divide-y divide-slate-800">
            {papers.map((paper) => (
              <div key={paper.id} className="flex items-center gap-4 px-5 py-3 hover:bg-slate-800/30 transition-colors">
                <FileText size={16} className="text-slate-500 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-slate-200 truncate">{paper.original_name}</div>
                  <div className="text-xs text-slate-600">{paper.page_count} pages · {paper.row_count} rows extracted</div>
                  {paper.error_message && (
                    <div className="text-xs text-red-400 mt-0.5 truncate">{paper.error_message}</div>
                  )}
                </div>
                <StatusBadge status={paper.status} />
                <div className="flex items-center gap-2">
                  {(paper.status === 'uploaded' || paper.status === 'error') && (
                    <button
                      onClick={() => handleExtractOne(paper.id)}
                      className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
                    >
                      <Zap size={12} /> Extract
                    </button>
                  )}
                  <button
                    onClick={() => handleDelete(paper.id, paper.original_name)}
                    className="text-xs text-slate-600 hover:text-red-400 transition-colors"
                  >
                    <XCircle size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
