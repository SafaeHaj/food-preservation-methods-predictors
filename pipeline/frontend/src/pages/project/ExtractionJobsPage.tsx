import { useParams, Link } from 'react-router-dom'
import { useCancelJob, useJobs } from '../../api/jobs'
import { errorMessage } from '../../api/errors'
import type { Job } from '../../types'
import { XCircle, Cpu, FlaskConical, Layers, ChevronRight, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'

// ─── Job type metadata ────────────────────────────────────────────────────────

const JOB_TYPE_META: Record<string, { label: string; color: string }> = {
  workspace_extraction: { label: 'Docling Extraction', color: 'bg-violet-50 text-violet-700' },
  llm_validation:       { label: 'LLM Validation',     color: 'bg-blue-50 text-blue-700' },
  training:             { label: 'Model Training',      color: 'bg-emerald-50 text-emerald-700' },
  export:               { label: 'Export',               color: 'bg-slate-100 text-slate-600' },
}

const STATUS_META: Record<string, { label: string; cls: string }> = {
  completed:       { label: 'Done',      cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  partial_success: { label: 'Partial',   cls: 'bg-amber-50 text-amber-700 border-amber-200' },
  failed:          { label: 'Failed',    cls: 'bg-red-50 text-red-600 border-red-200' },
  cancelled:       { label: 'Cancelled', cls: 'bg-slate-100 text-slate-500 border-slate-200' },
  queued:          { label: 'Queued',    cls: 'bg-sky-50 text-sky-700 border-sky-200' },
  running:         { label: 'Running',   cls: 'bg-blue-50 text-blue-700 border-blue-200' },
}

function StatusBadge({ status }: { status: string }) {
  const m = STATUS_META[status] ?? { label: status, cls: 'bg-slate-100 text-slate-500 border-slate-200' }
  return (
    <span className={clsx('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border', m.cls)}>
      {status === 'running' && <Loader2 size={9} className="animate-spin" />}
      {m.label}
    </span>
  )
}

function JobRow({ job, onCancel, projectId }: { job: Job; onCancel: (id: number) => void; projectId: string }) {
  const typeMeta = JOB_TYPE_META[job.job_type] ?? { label: job.job_type, color: 'bg-slate-100 text-slate-600' }
  const isActive = !['completed', 'failed', 'cancelled'].includes(job.status)

  return (
    <div className="flex items-start gap-3 py-3 px-4 border-b border-slate-100 last:border-0">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={clsx('text-[10px] font-semibold px-2 py-0.5 rounded-full', typeMeta.color)}>
            {typeMeta.label}
          </span>
          <StatusBadge status={job.status} />
          <span className="text-[10px] text-slate-400">#{job.id}</span>
        </div>
        {job.current_step && (
          <p className="text-xs text-slate-500 mt-1.5 leading-snug">{job.current_step}</p>
        )}
        {job.progress > 0 && job.progress < 100 && (
          <div className="mt-2 h-1 bg-slate-100 rounded-full overflow-hidden w-48">
            <div className="h-full bg-blue-500 rounded-full transition-all" style={{ width: `${job.progress}%` }} />
          </div>
        )}
        {job.error_message && (
          <p className="text-[10px] text-red-600 mt-1.5 font-mono bg-red-50 px-2 py-1 rounded-md">{job.error_message}</p>
        )}
        <p className="text-[10px] text-slate-300 mt-1.5">{new Date(job.created_at).toLocaleString()}</p>
      </div>
      {isActive && (
        <button
          onClick={() => onCancel(job.id)}
          title="Cancel job"
          className="p-1 text-slate-300 hover:text-red-500 transition-colors mt-0.5"
        >
          <XCircle size={14} />
        </button>
      )}
    </div>
  )
}

// ─── Paper group ──────────────────────────────────────────────────────────────

interface PaperGroup {
  paperId: number
  pipelineJobs: Job[]   // workspace_extraction + llm_validation
  legacyJobs: Job[]     // extraction
}

function PaperJobGroup({ group, onCancel, projectId }: { group: PaperGroup; onCancel: (id: number) => void; projectId: string }) {
  const hasActive = [...group.pipelineJobs, ...group.legacyJobs].some(
    (j) => !['completed', 'failed', 'cancelled'].includes(j.status),
  )

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
      {/* Paper header */}
      <div className="flex items-center gap-3 px-4 py-3 bg-slate-50 border-b border-slate-200">
        <Layers size={13} className="text-slate-400 shrink-0" />
        <span className="text-[12px] font-bold text-slate-700 flex-1">Paper #{group.paperId}</span>
        {hasActive && (
          <span className="flex items-center gap-1 text-[10px] text-blue-600 font-semibold">
            <Loader2 size={9} className="animate-spin" /> Active
          </span>
        )}
        <Link
          to={`/projects/${projectId}/papers/${group.paperId}/workspace`}
          className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-slate-700 font-medium"
        >
          Open workspace <ChevronRight size={10} />
        </Link>
      </div>

      {/* New pipeline jobs */}
      {group.pipelineJobs.length > 0 && (
        <div>
          <div className="px-4 pt-2 pb-0">
            <p className="text-[9px] font-bold uppercase tracking-widest text-slate-300 flex items-center gap-1.5">
              <Cpu size={9} /> New Pipeline
            </p>
          </div>
          {group.pipelineJobs.map((j) => (
            <JobRow key={j.id} job={j} onCancel={onCancel} projectId={projectId} />
          ))}
        </div>
      )}

      {/* Legacy jobs */}
      {group.legacyJobs.length > 0 && (
        <div className={group.pipelineJobs.length > 0 ? 'border-t border-dashed border-slate-200' : ''}>
          {group.pipelineJobs.length > 0 && (
            <div className="px-4 pt-2 pb-0">
              <p className="text-[9px] font-bold uppercase tracking-widest text-slate-300 flex items-center gap-1.5">
                <FlaskConical size={9} /> Legacy Pipeline
              </p>
            </div>
          )}
          {group.legacyJobs.map((j) => (
            <JobRow key={j.id} job={j} onCancel={onCancel} projectId={projectId} />
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ExtractionJobsPage() {
  const { projectId } = useParams<{ projectId: string }>()
  // No interval. The list is invalidated whenever a job stream reaches a terminal state,
  // so it stays current without polling every eight seconds for the life of the tab.
  const { data: jobs = [], isLoading: loading } = useJobs({
    project_id: Number(projectId),
    limit: 100,
  })
  const cancelJob = useCancelJob()

  const handleCancel = async (id: number) => {
    try {
      await cancelJob.mutateAsync(id)
      toast.success('Job cancelled')
    } catch (error) {
      toast.error(errorMessage(error, 'This job could not be cancelled'))
    }
  }

  // Group jobs by paper; jobs without a paper_id go in a separate bucket
  const paperMap = new Map<number | null, PaperGroup>()
  for (const job of jobs) {
    const key = job.paper_id ?? null
    if (!paperMap.has(key)) {
      paperMap.set(key, { paperId: key as number, pipelineJobs: [], legacyJobs: [] })
    }
    const grp = paperMap.get(key)!
    if (job.job_type === 'extraction') {
      grp.legacyJobs.push(job)
    } else {
      grp.pipelineJobs.push(job)
    }
  }
  const groups = Array.from(paperMap.values())
    .filter((g) => g.paperId != null)
    .sort((a, b) => b.paperId - a.paperId)

  const noJobsAtAll = !loading && jobs.length === 0

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Extraction Jobs</h1>
          <p className="text-xs text-slate-400 mt-0.5">All pipeline runs, grouped by paper</p>
        </div>
      </div>

      {loading && jobs.length === 0 ? (
        <div className="flex items-center gap-2 text-slate-400 py-8">
          <Loader2 size={14} className="animate-spin" /> Loading jobs…
        </div>
      ) : noJobsAtAll ? (
        <div className="text-center py-16 text-slate-300">
          <Layers size={40} strokeWidth={1} className="mx-auto mb-3" />
          <p className="text-sm text-slate-400">No jobs yet. Upload PDFs and run extractions.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {groups.map((g) => (
            <PaperJobGroup
              key={g.paperId}
              group={g}
              onCancel={handleCancel}
              projectId={projectId!}
            />
          ))}
        </div>
      )}
    </div>
  )
}
