/**
 * Project overview: the papers in a project and what has been extracted from them.
 *
 * Previously this page polled `GET /projects/{id}` and `GET /projects/{id}/papers` every
 * five seconds for as long as the tab was open — through a `setPapers` callback abused as
 * a state read — and carried the legacy "Extract All" and "Export to Excel" actions that
 * drove the deleted flat-extraction path.
 */

import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  AlertCircle, CheckCircle, ChevronRight, Clock, FileText, Microscope, Upload,
  XCircle,
} from 'lucide-react'
import toast from 'react-hot-toast'

import { useProject, useProjectStats } from '../api/projects'
import { useDeletePaper, usePapers } from '../api/papers'
import { errorMessage } from '../api/errors'
import type { Paper } from '../types'

const STATUS_STYLES: Record<string, { className: string; label: string }> = {
  uploaded: { className: 'badge-pending', label: 'Not analysed' },
  extracting: { className: 'badge-uploading', label: 'Extracting…' },
  extracted: { className: 'badge-extracted', label: 'Extracted' },
  reviewed: { className: 'badge-approved', label: 'Reviewed' },
  error: { className: 'badge-error', label: 'Failed' },
}

function StatusBadge({ status }: { status: Paper['status'] }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.uploaded
  return <span className={style.className}>{style.label}</span>
}

export default function ProjectView() {
  const { projectId } = useParams<{ projectId: string }>()
  const pid = Number(projectId)
  const [deleting, setDeleting] = useState<number | null>(null)

  const { data: project, isLoading, isError } = useProject(pid)
  const { data: papers = [] } = usePapers(pid)
  const { data: stats } = useProjectStats(pid)
  const deletePaper = useDeletePaper(pid)

  const handleDelete = async (paper: Paper) => {
    if (!confirm(`Delete "${paper.original_name}"? This also removes its extracted data.`)) return
    setDeleting(paper.id)
    try {
      await deletePaper.mutateAsync(paper.id)
      toast.success('Paper deleted')
    } catch (error) {
      toast.error(errorMessage(error, 'Could not delete the paper'))
    } finally {
      setDeleting(null)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-sm text-slate-500">Loading project…</p>
        </div>
      </div>
    )
  }

  if (isError || !project) {
    return (
      <div className="text-center py-24">
        <AlertCircle size={32} className="text-red-400 mx-auto mb-3" />
        <p className="text-slate-600">This project could not be loaded.</p>
      </div>
    )
  }

  const pending = papers.filter((p) => p.status === 'uploaded' || p.status === 'error')
  const extracted = papers.filter((p) => p.status === 'extracted' || p.status === 'reviewed')
  const errored = papers.filter((p) => p.status === 'error')

  const tiles = [
    { label: 'Papers', value: papers.length, icon: FileText, tone: 'bg-blue-50 text-blue-600' },
    { label: 'Extracted', value: extracted.length, icon: CheckCircle, tone: 'bg-emerald-50 text-emerald-600' },
    {
      label: 'Measurements',
      value: stats?.measurement_count ?? 0,
      icon: CheckCircle,
      tone: 'bg-violet-50 text-violet-600',
    },
    errored.length > 0
      ? { label: 'Failed', value: errored.length, icon: XCircle, tone: 'bg-red-50 text-red-500' }
      : { label: 'Not analysed', value: pending.length, icon: Clock, tone: 'bg-amber-50 text-amber-600' },
  ]

  return (
    <div className="space-y-6">
      <nav className="flex items-center gap-1.5 text-sm text-slate-500">
        <Link to="/" className="hover:text-slate-700 transition-colors">Projects</Link>
        <ChevronRight size={14} />
        <span className="text-slate-900 font-medium">{project.name}</span>
      </nav>

      <div className="flex flex-wrap items-start gap-4 justify-between">
        <div>
          <h1 className="page-title">{project.name}</h1>
          {project.description && <p className="muted mt-1">{project.description}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to={`/projects/${pid}/upload`} className="btn-primary">
            <Upload size={15} /> Upload PDFs
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {tiles.map(({ label, value, icon: Icon, tone }) => (
          <div key={label} className="stat-card">
            <div className={`stat-icon ${tone.split(' ')[0]}`}>
              <Icon size={18} className={tone.split(' ')[1]} />
            </div>
            <div>
              <div className="text-2xl font-bold text-slate-900">{value}</div>
              <div className="text-xs text-slate-500 mt-0.5">{label}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h2 className="section-title">Papers</h2>
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
                  <div className="text-sm font-medium text-slate-900 truncate">
                    {paper.original_name}
                  </div>
                  <div className="text-xs text-slate-400 mt-0.5">
                    {paper.page_count} pages
                    {paper.asset_count > 0 && <> · {paper.asset_count} elements</>}
                    {paper.experiment_count > 0 && (
                      <> · <span className="text-emerald-600 font-medium">
                        {paper.experiment_count} experiments
                      </span></>
                    )}
                  </div>
                  {paper.error_message && (
                    <div className="text-xs text-red-500 mt-1 flex items-center gap-1">
                      <AlertCircle size={11} /> {paper.error_message}
                    </div>
                  )}
                </div>

                <StatusBadge status={paper.status} />

                <div className="flex items-center gap-1">
                  <Link
                    to={`/projects/${pid}/papers/${paper.id}/workspace`}
                    className="btn-ghost text-xs py-1 px-2 text-blue-600 hover:bg-blue-50"
                  >
                    <Microscope size={11} /> Workspace
                  </Link>
                  <button
                    onClick={() => handleDelete(paper)}
                    disabled={deleting === paper.id}
                    className="p-1.5 text-slate-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
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
