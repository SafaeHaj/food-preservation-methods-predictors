import { useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import {
  AlertCircle, AlignLeft, BarChart3, BookOpen, Brain,
  CheckCircle2, ChevronDown, ChevronUp, FileText,
  Loader2, RefreshCw, Send, Table2, XCircle,
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { usePapers } from '../../api/papers'
import { useEvidencePackages, useSendToLlm } from '../../api/workspace'
import { errorMessage } from '../../api/errors'
import type {
  EvidenceAsset, EvidencePackages, EvidenceParagraph,
} from '../../types/workspace'
import { keys } from '../../api/keys'
import { useJobStream } from '../../hooks/useJobStream'
import { useLatestJob } from '../../hooks/useLatestJob'

// ─── Types ─────────────────────────────────────────────────────────────────────

// Types come from `types/workspace`, which mirrors the server's response models. They
// were previously redeclared here by hand and had already drifted from the payload.

// ─── Validation check helpers ──────────────────────────────────────────────────

function computeChecks(pkg: EvidencePackages | null) {
  if (!pkg) return []
  const t = pkg.totals
  return [
    {
      label: 'Assets extracted',
      ok: (t.paragraphs + t.native_tables + t.chart_csvs + t.excluded) > 0,
      detail: `${t.paragraphs + t.native_tables + t.chart_csvs + t.excluded} total assets`,
    },
    {
      label: 'Items selected for LLM',
      ok: (t.paragraphs + t.native_tables + t.chart_csvs) > 0,
      detail: `${t.paragraphs + t.native_tables + t.chart_csvs} selected`,
    },
    {
      label: 'Relevant paragraphs found',
      ok: t.paragraphs > 0,
      detail: `${t.paragraphs} text segment(s)`,
    },
    {
      label: 'Native tables present',
      ok: t.native_tables > 0,
      detail: `${t.native_tables} table(s)`,
    },
    {
      label: 'Chart CSV data available',
      ok: t.chart_csvs > 0,
      detail: `${t.chart_csvs} chart(s) converted`,
    },
    {
      label: 'Sufficient evidence for LLM',
      ok: (t.paragraphs + t.native_tables + t.chart_csvs) >= 2,
      detail: (t.paragraphs + t.native_tables + t.chart_csvs) >= 2
        ? 'Ready to send'
        : 'Need at least 2 evidence items',
    },
  ]
}

// ─── Donut chart (pure SVG, no library) ────────────────────────────────────────

function DonutChart({ paragraphs, tables, charts, excluded }: {
  paragraphs: number; tables: number; charts: number; excluded: number
}) {
  const total = paragraphs + tables + charts + excluded
  if (total === 0) {
    return (
      <div className="flex items-center justify-center h-28 text-slate-400 text-xs">
        No assets yet
      </div>
    )
  }
  const r = 40
  const cx = 60
  const cy = 60
  const circumference = 2 * Math.PI * r

  const segments = [
    { value: paragraphs, color: '#6366f1', label: 'Text' },
    { value: tables,     color: '#10b981', label: 'Tables' },
    { value: charts,     color: '#f59e0b', label: 'Charts' },
    { value: excluded,   color: '#94a3b8', label: 'Excluded' },
  ]

  let offset = 0
  const paths = segments.map((seg, i) => {
    const frac = seg.value / total
    const dash = frac * circumference
    const path = (
      <circle
        key={i}
        r={r}
        cx={cx}
        cy={cy}
        fill="none"
        stroke={seg.color}
        strokeWidth={18}
        strokeDasharray={`${dash} ${circumference - dash}`}
        strokeDashoffset={-offset}
        transform={`rotate(-90 ${cx} ${cy})`}
        style={{ transition: 'stroke-dasharray 0.4s' }}
      />
    )
    offset += dash
    return path
  })

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative">
        <svg width={120} height={120}>
          {paths}
          <text x={cx} y={cy - 4} textAnchor="middle" className="text-slate-900" fontSize={18} fontWeight="bold" fill="#0f172a">
            {total - excluded}
          </text>
          <text x={cx} y={cy + 14} textAnchor="middle" fontSize={9} fill="#64748b">
            selected
          </text>
        </svg>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 w-full">
        {segments.map((s) => (
          <div key={s.label} className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: s.color }} />
            <span className="text-[11px] text-slate-600">{s.label}: <b>{s.value}</b></span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Collapsible evidence section ──────────────────────────────────────────────

function EvidenceSection({
  icon: Icon,
  label,
  count,
  colorClass,
  children,
  defaultOpen = true,
}: {
  icon: React.ElementType
  label: string
  count: number
  colorClass: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 bg-white hover:bg-slate-50 transition-colors"
      >
        <div className="flex items-center gap-2.5">
          <div className={clsx('w-7 h-7 rounded-lg flex items-center justify-center', colorClass)}>
            <Icon size={14} />
          </div>
          <span className="font-semibold text-sm text-slate-800">{label}</span>
          <span className="px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded-full font-medium">
            {count}
          </span>
        </div>
        {open ? <ChevronUp size={14} className="text-slate-400" /> : <ChevronDown size={14} className="text-slate-400" />}
      </button>
      {open && <div className="border-t border-slate-100 divide-y divide-slate-100">{children}</div>}
    </div>
  )
}

// ─── Paragraph row ──────────────────────────────────────────────────────────────

function ParagraphRow({ item }: { item: EvidenceParagraph }) {
  const [expanded, setExpanded] = useState(false)
  const badge = {
    neighbor_before: 'Before',
    neighbor_after: 'After',
    keyword_match: 'Keyword',
    same_section: 'Section',
  }[item.link_type] || item.link_type

  return (
    <div className="px-4 py-3 bg-white hover:bg-slate-50 transition-colors">
      <div className="flex items-start gap-3">
        <div className="shrink-0 mt-0.5">
          <AlignLeft size={13} className="text-indigo-400" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="text-[10px] px-1.5 py-0.5 bg-indigo-50 text-indigo-600 rounded font-medium">
              {badge}
            </span>
            {item.section_name && (
              <span className="text-[10px] text-slate-400 truncate max-w-[180px]">{item.section_name}</span>
            )}
            <span className="text-[10px] text-slate-400 ml-auto">p.{item.page_number}</span>
          </div>
          <p className={clsx('text-xs text-slate-700 leading-relaxed', !expanded && 'line-clamp-2')}>
            {item.text}
          </p>
          {item.text.length > 160 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-[10px] text-blue-500 hover:text-blue-700 mt-1"
            >
              {expanded ? 'Show less' : 'Show more'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Asset row ─────────────────────────────────────────────────────────────────

function AssetRow({ item, type }: { item: EvidenceAsset; type: 'table' | 'chart' | 'excluded' }) {
  const [expanded, setExpanded] = useState(false)
  const colorMap = {
    table: 'text-emerald-500',
    chart: 'text-amber-500',
    excluded: 'text-slate-400',
  }
  const Icon = type === 'table' ? Table2 : type === 'chart' ? BarChart3 : FileText

  return (
    <div className="px-4 py-3 bg-white hover:bg-slate-50 transition-colors">
      <div className="flex items-start gap-3">
        <Icon size={14} className={clsx('mt-0.5 shrink-0', colorMap[type])} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5 flex-wrap">
            <span className="text-xs font-medium text-slate-800 truncate">
              {item.caption || `${type === 'table' ? 'Table' : 'Chart'} (page ${item.page_number})`}
            </span>
            <span className="ml-auto text-[10px] text-slate-400">p.{item.page_number}</span>
          </div>
          <div className="flex items-center gap-3">
            {item.csv_rows != null && (
              <span className="text-[10px] text-slate-500">{item.csv_rows} rows × {item.csv_cols} cols</span>
            )}
            {item.link_count > 0 && (
              <span className="text-[10px] text-slate-500">{item.link_count} context link(s)</span>
            )}
            <span className={clsx(
              'text-[10px] px-1.5 py-0.5 rounded font-medium ml-auto',
              item.relevance_score >= 7 ? 'bg-green-50 text-green-700' :
              item.relevance_score >= 4 ? 'bg-amber-50 text-amber-700' :
              'bg-slate-100 text-slate-500'
            )}>
              Score {item.relevance_score?.toFixed(1)}
            </span>
          </div>
          {item.context_links.length > 0 && (
            <>
              <button
                onClick={() => setExpanded(!expanded)}
                className="text-[10px] text-blue-500 hover:text-blue-700 mt-1"
              >
                {expanded ? 'Hide context' : `Show ${item.context_links.length} context link(s)`}
              </button>
              {expanded && (
                <div className="mt-2 space-y-1.5 pl-2 border-l-2 border-blue-100">
                  {item.context_links.slice(0, 4).map((lnk) => (
                    <p key={lnk.id} className="text-[11px] text-slate-600 leading-relaxed line-clamp-2">
                      {lnk.text}
                    </p>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Main page ─────────────────────────────────────────────────────────────────

export default function ValidationPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const pid = Number(projectId)

  const [paperId, setPaperId] = useState<number | null>(null)
  // ── Papers ──────────────────────────────────────────────────────────────────

  const { data: allPapers = [] } = usePapers(pid)

  // Prefer papers that have actually been through Docling; fall back to all of them so a
  // project whose papers are all still queued does not present an empty picker.
  const papers = useMemo(() => {
    const analysed = allPapers.filter((p) => ['extracted', 'extracting'].includes(p.status))
    return analysed.length > 0 ? analysed : allPapers
  }, [allPapers])

  useEffect(() => {
    const requested = searchParams.get('paperId')
    if (requested) setPaperId(Number(requested))
    else if (paperId === null && papers.length > 0) setPaperId(papers[0].id)
  }, [searchParams, papers, paperId])

  // ── Evidence ────────────────────────────────────────────────────────────────

  const {
    data: pkgData = null,
    isLoading: loading,
  } = useEvidencePackages(pid, paperId ?? 0, paperId !== null)

  // ── LLM job ─────────────────────────────────────────────────────────────────

  const sendToLlm = useSendToLlm(pid, paperId ?? 0)
  const { jobId: existingJobId } = useLatestJob(pid, paperId ?? 0, 'llm_validation')
  const jobId = sendToLlm.data?.job_id ?? existingJobId

  const { progress: job } = useJobStream(jobId, {
    // The ingestion job writes ext_* rows and promotes them into the canonical hierarchy,
    // so the scientific database views are stale the moment it finishes.
    invalidateOnComplete: [
      keys.workspace.all(pid, paperId ?? 0),
      keys.studies.all(pid),
      keys.observations.all(pid),
      keys.projects.stats(pid),
    ],
    onComplete: (final) => {
      if (final.status === 'completed') toast.success('Extraction complete')
    },
    onError: (message) => toast.error(`Extraction failed: ${message}`),
  })

  const sending = sendToLlm.isPending

  // The job result is an untyped payload on the wire; narrow it once here rather than
  // casting at each of the four places it is rendered.
  const ingestion = job?.result
    ? {
        experiments: Number(job.result.experiments ?? 0),
        measurements: Number(job.result.measurements ?? 0),
        lowConfidence: Number(job.result.low_confidence_count ?? 0),
        reasoning: String(job.result.reasoning ?? ''),
      }
    : null

  const handleSend = async () => {
    if (!paperId) return
    try {
      await sendToLlm.mutateAsync()
      toast.success('Sent for extraction')
    } catch (error) {
      toast.error(errorMessage(error, 'Could not start LLM extraction'))
    }
  }

  // ── Derived state ────────────────────────────────────────────────────────────

  const checks = computeChecks(pkgData)
  const allChecksPass = checks.length > 0 && checks.every((c) => c.ok)
  const isRunning = !!job && ['queued', 'running'].includes(job.status)
  const canSend = !isRunning && !sending && paperId !== null &&
    pkgData !== null &&
    (pkgData.totals.paragraphs + pkgData.totals.native_tables + pkgData.totals.chart_csvs) > 0

  const selectedPaper = papers.find((p) => p.id === paperId)

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-200 bg-white flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Validation</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Review evidence packages and send selected content to Llama 4 for extraction
          </p>
        </div>

        {/* Paper selector */}
        <div className="flex items-center gap-3">
          <label className="text-xs font-semibold text-slate-600">Paper:</label>
          <select
            value={paperId ?? ''}
            onChange={(e) => setPaperId(Number(e.target.value))}
            className="text-sm border border-slate-300 rounded-lg px-3 py-1.5 bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500 max-w-[280px] truncate"
          >
            <option value="">Select a paper…</option>
            {papers.map((p) => (
              <option key={p.id} value={p.id}>{p.original_name}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Body */}
      {!paperId ? (
        <div className="flex-1 flex items-center justify-center text-slate-400">
          <div className="text-center">
            <BookOpen size={40} className="mx-auto mb-3 opacity-30" />
            <p className="text-sm">Select a paper to view its evidence packages</p>
          </div>
        </div>
      ) : loading ? (
        <div className="flex-1 flex items-center justify-center">
          <Loader2 size={28} className="animate-spin text-blue-500" />
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto">
          <div className="flex gap-0 h-full">
            {/* ── Left: Evidence packages (2/3) ─────────────────────────────── */}
            <div className="flex-1 min-w-0 overflow-y-auto p-5 space-y-4 border-r border-slate-200">

              {/* LLM job status banner */}
              {job && (
                <div className={clsx(
                  'rounded-xl p-4 border flex items-start gap-3',
                  job.status === 'completed' ? 'bg-green-50 border-green-200' :
                  job.status === 'failed'    ? 'bg-red-50 border-red-200' :
                  'bg-blue-50 border-blue-200'
                )}>
                  {job.status === 'completed' ? (
                    <CheckCircle2 size={18} className="text-green-600 mt-0.5 shrink-0" />
                  ) : job.status === 'failed' ? (
                    <XCircle size={18} className="text-red-600 mt-0.5 shrink-0" />
                  ) : (
                    <Loader2 size={18} className="text-blue-600 mt-0.5 shrink-0 animate-spin" />
                  )}
                  <div className="flex-1">
                    <p className={clsx(
                      'text-sm font-semibold',
                      job.status === 'completed' ? 'text-green-800' :
                      job.status === 'failed'    ? 'text-red-800' :
                      'text-blue-800'
                    )}>
                      {job.status === 'completed' ? 'LLM Extraction Complete' :
                       job.status === 'failed'    ? 'Extraction Failed' :
                       'LLM Extraction Running…'}
                    </p>
                    <p className="text-xs text-slate-600 mt-0.5">{job.current_step}</p>
                    {isRunning && (
                      <div className="mt-2 h-1.5 bg-blue-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-blue-500 rounded-full transition-all duration-500"
                          style={{ width: `${job.progress}%` }}
                        />
                      </div>
                    )}
                    {ingestion && job.status === 'completed' && (
                      <div className="mt-2 flex gap-4 flex-wrap">
                        <span className="text-xs text-green-700 font-medium">
                          {ingestion.experiments} experiment(s)
                        </span>
                        <span className="text-xs text-green-700 font-medium">
                          {ingestion.measurements} measurement(s)
                        </span>
                        {ingestion.lowConfidence > 0 && (
                          <span className="text-xs text-amber-600">
                            {ingestion.lowConfidence} low-confidence
                          </span>
                        )}
                        <button
                          onClick={() => navigate(`/projects/${pid}/experiments`)}
                          className="text-xs text-blue-600 font-semibold hover:underline"
                        >
                          View results →
                        </button>
                      </div>
                    )}
                    {job.status === 'failed' && job.error && (
                      <p className="text-xs text-red-600 mt-1">{job.error}</p>
                    )}
                  </div>
                </div>
              )}

              {pkgData === null ? (
                <div className="flex flex-col items-center justify-center py-16 text-slate-400">
                  <AlertCircle size={36} className="mb-3 opacity-30" />
                  <p className="text-sm font-medium">No extracted assets found</p>
                  <p className="text-xs mt-1">Run the Docling pipeline for this paper first</p>
                  <button
                    onClick={() => navigate(`/projects/${pid}/jobs`)}
                    className="mt-4 btn-secondary text-xs"
                  >
                    Go to Pipeline
                  </button>
                </div>
              ) : (
                <>
                  <p className="text-xs text-slate-500 px-1">
                    Evidence below is ranked by relevance score. Items marked as{' '}
                    <strong>Selected for LLM</strong> in the workspace will be included.
                  </p>

                  {/* Relevant Paragraphs */}
                  <EvidenceSection
                    icon={AlignLeft}
                    label="Relevant Paragraphs"
                    count={pkgData.totals.paragraphs}
                    colorClass="bg-indigo-100 text-indigo-600"
                  >
                    {pkgData.paragraphs.length === 0 ? (
                      <div className="px-4 py-3 text-xs text-slate-400">
                        No relevant text paragraphs found
                      </div>
                    ) : (
                      pkgData.paragraphs.slice(0, 30).map((item, i) => (
                        <ParagraphRow key={`${item.asset_id}-${item.link_id}-${i}`} item={item} />
                      ))
                    )}
                    {pkgData.paragraphs.length > 30 && (
                      <div className="px-4 py-2 text-xs text-slate-400 bg-slate-50">
                        + {pkgData.paragraphs.length - 30} more paragraphs
                      </div>
                    )}
                  </EvidenceSection>

                  {/* Native Tables */}
                  <EvidenceSection
                    icon={Table2}
                    label="Native Tables"
                    count={pkgData.totals.native_tables}
                    colorClass="bg-emerald-100 text-emerald-600"
                  >
                    {pkgData.native_tables.length === 0 ? (
                      <div className="px-4 py-3 text-xs text-slate-400">No native tables found</div>
                    ) : (
                      pkgData.native_tables.map((item) => (
                        <AssetRow key={item.id} item={item} type="table" />
                      ))
                    )}
                  </EvidenceSection>

                  {/* Chart CSV Files */}
                  <EvidenceSection
                    icon={BarChart3}
                    label="Chart CSV Files"
                    count={pkgData.totals.chart_csvs}
                    colorClass="bg-amber-100 text-amber-600"
                  >
                    {pkgData.chart_csvs.length === 0 ? (
                      <div className="px-4 py-3 text-xs text-slate-400">
                        No chart CSVs available
                      </div>
                    ) : (
                      pkgData.chart_csvs.map((item) => (
                        <AssetRow key={item.id} item={item} type="chart" />
                      ))
                    )}
                  </EvidenceSection>

                  {/* Excluded Items */}
                  {pkgData.excluded.length > 0 && (
                    <EvidenceSection
                      icon={FileText}
                      label="Excluded Items"
                      count={pkgData.totals.excluded}
                      colorClass="bg-slate-100 text-slate-500"
                      defaultOpen={false}
                    >
                      {pkgData.excluded.map((item) => (
                        <AssetRow key={item.id} item={item} type="excluded" />
                      ))}
                    </EvidenceSection>
                  )}
                </>
              )}
            </div>

            {/* ── Right: Checks + summary + action (1/3) ──────────────────────── */}
            <div className="w-80 shrink-0 overflow-y-auto p-5 space-y-5 bg-slate-50">

              {/* Local Validation Checks */}
              <div className="card">
                <h3 className="section-title mb-3">Local Validation Checks</h3>
                <div className="space-y-2">
                  {checks.map((c) => (
                    <div key={c.label} className="flex items-start gap-2.5">
                      {c.ok ? (
                        <CheckCircle2 size={15} className="text-emerald-500 mt-0.5 shrink-0" />
                      ) : (
                        <XCircle size={15} className="text-red-400 mt-0.5 shrink-0" />
                      )}
                      <div className="min-w-0">
                        <p className="text-xs font-medium text-slate-800 leading-tight">{c.label}</p>
                        <p className="text-[10px] text-slate-500 mt-0.5">{c.detail}</p>
                      </div>
                    </div>
                  ))}
                </div>
                {pkgData && (
                  <div className={clsx(
                    'mt-3 pt-3 border-t border-slate-100 flex items-center gap-2',
                    allChecksPass ? 'text-emerald-600' : 'text-amber-600'
                  )}>
                    {allChecksPass ? <CheckCircle2 size={13} /> : <AlertCircle size={13} />}
                    <span className="text-[11px] font-semibold">
                      {allChecksPass ? 'All checks passed' : 'Some checks need attention'}
                    </span>
                  </div>
                )}
              </div>

              {/* Selection Summary */}
              {pkgData && (
                <div className="card">
                  <h3 className="section-title mb-3">Selection Summary</h3>
                  <DonutChart
                    paragraphs={pkgData.totals.paragraphs}
                    tables={pkgData.totals.native_tables}
                    charts={pkgData.totals.chart_csvs}
                    excluded={pkgData.totals.excluded}
                  />
                </div>
              )}

              {/* Send to LLM */}
              <div className="card space-y-3">
                <h3 className="section-title">Send to Llama 4</h3>
                <p className="text-xs text-slate-500">
                  Selected evidence will be packaged and sent to{' '}
                  <strong>llama-3.3-70b-versatile</strong> via Groq for food-safety
                  data extraction. Results are saved to the database.
                </p>

                {isRunning ? (
                  <div className="space-y-2">
                    <div className="h-2 bg-blue-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-500 rounded-full transition-all duration-500"
                        style={{ width: `${job!.progress}%` }}
                      />
                    </div>
                    <p className="text-xs text-blue-700 font-medium">{job!.current_step}</p>
                    <p className="text-[10px] text-slate-400">{job!.progress}% complete</p>
                  </div>
                ) : (
                  <button
                    onClick={handleSend}
                    disabled={!canSend || sending}
                    className={clsx(
                      'w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold transition-all',
                      canSend && !sending
                        ? 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm'
                        : 'bg-slate-100 text-slate-400 cursor-not-allowed'
                    )}
                  >
                    {sending ? (
                      <Loader2 size={15} className="animate-spin" />
                    ) : (
                      <Brain size={15} />
                    )}
                    {sending ? 'Starting…' : 'Send Selected Evidence to Llama 4'}
                    {!sending && <Send size={13} />}
                  </button>
                )}

                {!canSend && !isRunning && pkgData !== null && (
                  <p className="text-[10px] text-amber-600 text-center">
                    Select at least one item in the workspace first
                  </p>
                )}

                {selectedPaper && (
                  <button
                    onClick={() => navigate(`/projects/${pid}/jobs`)}
                    className="w-full text-xs text-slate-500 hover:text-slate-700 text-center"
                  >
                    View all jobs →
                  </button>
                )}
              </div>

              {/* Reasoning summary */}
              {ingestion?.reasoning && job?.status === 'completed' && (
                <div className="card">
                  <h3 className="section-title mb-2">LLM Reasoning</h3>
                  <p className="text-xs text-slate-600 leading-relaxed line-clamp-8">
                    {ingestion.reasoning}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
