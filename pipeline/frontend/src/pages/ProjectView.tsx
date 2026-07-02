import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  Upload, Settings, Eye, BarChart2, Download, FileText,
  CheckCircle, XCircle, Clock, Zap, ChevronRight, AlertCircle
} from 'lucide-react'
import toast from 'react-hot-toast'
import { projectsApi, papersApi, extractionApi, exportApi } from '../services/api'
import { Project, Paper } from '../types'

const StatusBadge = ({ status }: { status: Paper['status'] }) => {
  const map: Record<string, string> = {
    uploaded: 'badge-pending',
    extracting: 'badge-uploading',
    extracted: 'badge-extracted',
    reviewed: 'badge-approved',
    error: 'badge-error',
  }
  const labels: Record<string, string> = {
    uploaded: 'Pending',
    extracting: 'Extracting…',
    extracted: 'Extracted',
    reviewed: 'Reviewed',
    error: 'Error',
  }
  return <span className={map[status] || 'badge-pending'}>{labels[status] ?? status}</span>
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
      setPapers((prev) => {
        if (prev.some((p) => p.status === 'extracting')) { load() }
        return prev
      })
    }, 5000)
    return () => clearInterval(interval)
  }, [pid])

  const handleExtractAll = async () => {
    try {
      await extractionApi.extractAll(pid)
      toast.success('AI extraction started')
      setTimeout(load, 2000)
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Extraction failed')
    }
  }

  const handleExtractOne = async (paperId: number) => {
    try {
      await extractionApi.extractOne(pid, paperId)
      toast.success('Extraction started')
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

  if (loading) return (
    <div className="flex items-center justify-center py-24">
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-sm text-slate-500">Loading project…</p>
      </div>
    </div>
  )

  if (!project) return (
    <div className="text-center py-24">
      <AlertCircle size={32} className="text-red-400 mx-auto mb-3" />
      <p className="text-slate-600">Project not found</p>
    </div>
  )

  const pending = papers.filter((p) => p.status === 'uploaded' || p.status === 'error')
  const extracted = papers.filter((p) => p.status === 'extracted' || p.status === 'reviewed')
  const errors = papers.filter((p) => p.status === 'error')
  const totalRows = papers.reduce((s, p) => s + (p.row_count || 0), 0)

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-sm text-slate-500">
        <Link to="/" className="hover:text-slate-700 transition-colors">Projects</Link>
        <ChevronRight size={14} />
        <span className="text-slate-900 font-medium">{project.name}</span>
      </nav>

      {/* Header */}
      <div className="flex flex-wrap items-start gap-4 justify-between">
        <div>
          <h1 className="page-title">{project.name}</h1>
          {project.description && <p className="muted mt-1">{project.description}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to={`/projects/${pid}/upload`} className="btn-primary">
            <Upload size={15} /> Upload PDFs
          </Link>
          <Link to={`/projects/${pid}/schema`} className="btn-secondary">
            <Settings size={15} /> Schema
          </Link>
          <Link to={`/projects/${pid}/review`} className="btn-secondary">
            <Eye size={15} /> Review
          </Link>
          <Link to={`/projects/${pid}/analytics`} className="btn-secondary">
            <BarChart2 size={15} /> Analytics
          </Link>
          <button onClick={handleExport} className="btn-secondary">
            <Download size={15} /> Export
          </button>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Total Papers', value: papers.length, icon: FileText, color: 'bg-blue-50', iconColor: 'text-blue-600' },
          { label: 'Extracted', value: extracted.length, icon: CheckCircle, color: 'bg-emerald-50', iconColor: 'text-emerald-600' },
          { label: 'Total Rows', value: totalRows, icon: CheckCircle, color: 'bg-violet-50', iconColor: 'text-violet-600' },
          { label: errors.length > 0 ? 'Errors' : 'Pending', value: errors.length > 0 ? errors.length : pending.length, icon: errors.length > 0 ? XCircle : Clock, color: errors.length > 0 ? 'bg-red-50' : 'bg-amber-50', iconColor: errors.length > 0 ? 'text-red-500' : 'text-amber-600' },
        ].map(({ label, value, icon: Icon, color, iconColor }) => (
          <div key={label} className="stat-card">
            <div className={`stat-icon ${color}`}>
              <Icon size={18} className={iconColor} />
            </div>
            <div>
              <div className="text-2xl font-bold text-slate-900">{value}</div>
              <div className="text-xs text-slate-500 mt-0.5">{label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Papers table */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h2 className="section-title">Papers</h2>
          {pending.length > 0 && (
            <button onClick={handleExtractAll} className="btn-primary text-xs py-1.5 gap-1.5">
              <Zap size={13} />
              Extract All ({pending.length})
            </button>
          )}
        </div>
        {papers.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-12 h-12 bg-slate-50 rounded-xl flex items-center justify-center mx-auto mb-4">
              <FileText size={20} className="text-slate-300" />
            </div>
            <p className="text-sm text-slate-500 mb-4">No papers yet</p>
            <Link to={`/projects/${pid}/upload`} className="btn-primary text-xs">
              <Upload size={13} /> Upload PDFs
            </Link>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {papers.map((paper) => (
              <div
                key={paper.id}
                className="flex items-center gap-4 px-6 py-4 hover:bg-slate-50 transition-colors group"
              >
                <div className="w-8 h-8 bg-blue-50 rounded-lg flex items-center justify-center shrink-0">
                  <FileText size={14} className="text-blue-500" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-slate-900 truncate">{paper.original_name}</div>
                  <div className="text-xs text-slate-400 mt-0.5">
                    {paper.page_count} pages
                    {paper.row_count > 0 && <> · <span className="text-emerald-600 font-medium">{paper.row_count} rows extracted</span></>}
                  </div>
                  {paper.error_message && (
                    <div className="text-xs text-red-500 mt-1 flex items-center gap-1">
                      <AlertCircle size={11} /> {paper.error_message}
                    </div>
                  )}
                </div>
                <StatusBadge status={paper.status} />
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  {(paper.status === 'uploaded' || paper.status === 'error') && (
                    <button
                      onClick={() => handleExtractOne(paper.id)}
                      className="btn-ghost text-xs py-1 px-2 text-blue-600 hover:bg-blue-50"
                    >
                      <Zap size={11} /> Extract
                    </button>
                  )}
                  <button
                    onClick={() => handleDelete(paper.id, paper.original_name)}
                    className="p-1.5 text-slate-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
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
