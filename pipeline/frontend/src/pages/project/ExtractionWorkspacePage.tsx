/**
 * Extraction workspace.
 *
 * Request lifecycle for opening one paper — the whole point of the refactor:
 *
 *   GET  /projects/{id}/papers/{paperId}            usePaper
 *   POST /projects/{id}/papers/{paperId}/workspace  useStartExtraction (only when needed)
 *   SSE  /jobs/{jobId}/events                       useJobStream
 *   GET  /projects/{id}/papers/{paperId}/assets     useAssets, gated on completion
 *
 * Previously this page polled a status endpoint every 2.5 seconds and refetched all 200
 * assets on every tick, started a second interval through a racing ref guard, and left
 * both running when the user navigated away.
 */

import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  AlertCircle, ArrowLeft, BarChart2, BarChart3, ChevronRight, CheckCircle2, Circle,
  FileText, FileType2, Filter, Image, LayoutGrid, Layers, Loader2, RefreshCw, Star, Table2,
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

import { usePaper } from '../../api/papers'
import { useAssets, useStartExtraction, useUpdateAsset } from '../../api/workspace'
import { errorMessage } from '../../api/errors'
import { keys } from '../../api/keys'
import { useJobStream } from '../../hooks/useJobStream'
import { useLatestJob } from '../../hooks/useLatestJob'
import AssetCard from '../../components/AssetCard'
import AssetDetailPanel from '../../components/AssetDetailPanel'
import type { ExtractionAsset } from '../../types/workspace'

const WORKSPACE_JOB_TYPE = 'workspace_extraction'

/**
 * Stage labels shown while the pipeline runs.
 *
 * These mirror `extraction/app/services/docling_pipeline.STAGES`. The percentages are the
 * server's, not the client's: previously the frontend invented its own progress thresholds
 * and the two drifted apart, so the bar and the step text disagreed.
 */
const PIPELINE_STAGES = [
  { id: 'parse', label: 'Document parsing', at: 5 },
  { id: 'pages', label: 'Page rendering', at: 25 },
  { id: 'assets', label: 'Figures & tables', at: 35 },
  { id: 'linking', label: 'Context linking', at: 50 },
  { id: 'charts', label: 'Chart conversion', at: 65 },
  { id: 'scoring', label: 'Classification & scoring', at: 85 },
  { id: 'manifest', label: 'Manifest', at: 95 },
]

const FILTERS = [
  { id: 'all', label: 'All', icon: <Layers size={12} /> },
  { id: 'chart', label: 'Charts', icon: <BarChart2 size={12} /> },
  { id: 'native_table', label: 'Tables', icon: <Table2 size={12} /> },
  { id: 'figure', label: 'Figures', icon: <Image size={12} /> },
  { id: 'photograph', label: 'Photos', icon: <Image size={12} /> },
  { id: 'diagram', label: 'Diagrams', icon: <Image size={12} /> },
]

function stageState(progress: number, index: number): 'done' | 'active' | 'pending' {
  const stage = PIPELINE_STAGES[index]
  const next = PIPELINE_STAGES[index + 1]
  if (progress >= (next?.at ?? 100)) return 'done'
  if (progress >= stage.at) return 'active'
  return 'pending'
}

export default function ExtractionWorkspacePage() {
  const { projectId, paperId } = useParams<{ projectId: string; paperId: string }>()
  const pid = Number(projectId)
  const paperIdNum = Number(paperId)
  const navigate = useNavigate()

  const [activeFilter, setActiveFilter] = useState('all')
  const [selectedAsset, setSelectedAsset] = useState<ExtractionAsset | null>(null)

  const { data: paper } = usePaper(pid, paperIdNum)

  // Reconnect to an extraction already running (or finished) for this paper, so a refresh
  // or a second tab attaches to it instead of starting a duplicate parse.
  const { jobId: existingJobId, isLoading: jobLoading } = useLatestJob(
    pid, paperIdNum, WORKSPACE_JOB_TYPE,
  )
  const startExtraction = useStartExtraction(pid, paperIdNum)
  const activeJobId = startExtraction.data?.job_id ?? existingJobId

  const { progress, isRunning, isComplete, isFailed } = useJobStream(activeJobId, {
    invalidateOnComplete: [keys.workspace.all(pid, paperIdNum), keys.papers.all(pid)],
    onError: (message) => toast.error(`Extraction failed: ${message}`),
  })

  // The single most important line on this page: assets are not requested until there are
  // assets to request.
  const { data: assetPage } = useAssets(pid, paperIdNum, {}, { enabled: isComplete })
  const assets = useMemo(() => assetPage?.items ?? [], [assetPage])

  const updateAsset = useUpdateAsset(pid, paperIdNum)

  const handleToggleSelect = (asset: ExtractionAsset, value: boolean) =>
    updateAsset
      .mutateAsync({ assetId: asset.id, selected_for_llm: value })
      .catch((error) => toast.error(errorMessage(error, 'Could not update the selection')))

  const handleStart = () =>
    startExtraction
      .mutateAsync()
      .catch((error) => toast.error(errorMessage(error, 'Could not start extraction')))

  const filteredAssets = assets.filter((asset) => {
    if (activeFilter === 'all') return true
    if (activeFilter === 'figure') return asset.asset_type === 'figure'
    return asset.classification === activeFilter
  })

  const selectedCount = assets.filter((asset) => asset.selected_for_llm).length
  const percent = progress?.progress ?? 0
  const paperName = paper?.original_name ?? `Paper ${paperIdNum}`
  const summary = progress?.result as Record<string, number> | undefined

  // ── Idle: no extraction has been run for this paper yet ─────────────────────
  if (!jobLoading && !activeJobId) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-5">
        <div className="w-14 h-14 bg-blue-50 rounded-full flex items-center justify-center">
          <FileType2 size={24} className="text-blue-500" />
        </div>
        <div className="text-center">
          <h2 className="text-base font-bold text-slate-700">{paperName}</h2>
          <p className="text-sm text-slate-400 mt-1">
            This paper has not been analysed yet.
          </p>
        </div>
        <div className="flex gap-3">
          <Link to={`/projects/${pid}`} className="btn-secondary text-sm">
            <ArrowLeft size={13} /> Back
          </Link>
          <button
            onClick={handleStart}
            disabled={startExtraction.isPending}
            className="btn-primary text-sm"
          >
            {startExtraction.isPending
              ? <><Loader2 size={13} className="animate-spin" /> Starting…</>
              : <><BarChart3 size={13} /> Analyse document</>}
          </button>
        </div>
      </div>
    )
  }

  // ── Failed ──────────────────────────────────────────────────────────────────
  if (isFailed) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-5">
        <div className="w-14 h-14 bg-red-50 rounded-full flex items-center justify-center">
          <AlertCircle size={24} className="text-red-400" />
        </div>
        <div className="text-center">
          <h2 className="text-base font-bold text-slate-700">Extraction failed</h2>
          <p className="text-sm text-red-500 mt-1 max-w-md">
            {progress?.error ?? 'Unknown error'}
          </p>
        </div>
        <div className="flex gap-3">
          <Link to={`/projects/${pid}`} className="btn-secondary text-sm">
            <ArrowLeft size={13} /> Back
          </Link>
          <button onClick={handleStart} className="btn-primary text-sm">
            <RefreshCw size={13} /> Retry
          </button>
        </div>
      </div>
    )
  }

  // ── Running ─────────────────────────────────────────────────────────────────
  if (!isComplete) {
    return (
      <div className="flex flex-col h-full bg-white">
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-200 shrink-0">
          <Link
            to={`/projects/${pid}`}
            className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg"
          >
            <ArrowLeft size={16} />
          </Link>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-bold text-slate-900 truncate">{paperName}</h1>
              <span className="flex items-center gap-1 text-[10px] font-semibold text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-100">
                <Loader2 size={9} className="animate-spin" /> Running
              </span>
            </div>
            {progress?.current_step && (
              <p className="text-[11px] text-slate-400 mt-0.5 truncate">{progress.current_step}</p>
            )}
          </div>
          <div className="shrink-0 flex items-center gap-3">
            <span className="text-sm font-bold text-slate-700">{percent}%</span>
            <div className="w-28 h-2 bg-slate-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full transition-all duration-700"
                style={{ width: `${percent}%` }}
              />
            </div>
          </div>
        </div>

        <div className="flex-1 flex items-center justify-center">
          <div className="w-full max-w-sm px-6">
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-4">
              Pipeline
            </p>
            <div className="space-y-3">
              {PIPELINE_STAGES.map((stage, index) => {
                const state = stageState(percent, index)
                return (
                  <div key={stage.id} className="flex items-center gap-2.5">
                    {state === 'done' ? (
                      <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
                    ) : state === 'active' ? (
                      <Loader2 size={14} className="text-blue-500 animate-spin shrink-0" />
                    ) : (
                      <Circle size={14} className="text-slate-200 shrink-0" />
                    )}
                    <span
                      className={clsx(
                        'text-[12px]',
                        state === 'done' ? 'text-slate-600'
                          : state === 'active' ? 'text-blue-700 font-semibold'
                          : 'text-slate-300',
                      )}
                    >
                      {stage.label}
                    </span>
                  </div>
                )
              })}
            </div>
            <p className="text-[11px] text-slate-400 mt-6">
              {isRunning
                ? 'You can leave this page; the job keeps running.'
                : 'Waiting for a worker to pick up the job…'}
            </p>
          </div>
        </div>
      </div>
    )
  }

  // ── Completed: the asset explorer ───────────────────────────────────────────
  return (
    <div className="flex flex-col h-full bg-white">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-200 shrink-0">
        <Link
          to={`/projects/${pid}`}
          className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg"
        >
          <ArrowLeft size={16} />
        </Link>
        <div className="flex-1 min-w-0">
          <h1 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <span className="truncate">{paperName}</span>
            <span className="text-[10px] font-semibold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-100 shrink-0">
              Complete
            </span>
          </h1>
          {summary && (
            <p className="text-[11px] text-slate-400 mt-0.5">
              {summary.page_count} pages · {summary.figures} figures · {summary.charts} charts
              {' '}· {summary.native_tables} tables
              {summary.decorative_excluded
                ? ` · ${summary.decorative_excluded} decorative excluded`
                : ''}
            </p>
          )}
        </div>
        <Link
          to={`/projects/${pid}/papers/${paperIdNum}/chart2table`}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 text-slate-600 rounded-lg text-xs font-semibold hover:bg-slate-200 transition-colors"
        >
          <BarChart3 size={12} /> Charts
        </Link>
        <button
          onClick={() => navigate(`/projects/${pid}/validation?paperId=${paperIdNum}`)}
          className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-semibold hover:bg-blue-700 transition-colors"
        >
          <Star size={12} />
          {selectedCount > 0 ? `${selectedCount} selected` : 'Review evidence'}
          <ChevronRight size={11} />
        </button>
      </div>

      <div className="flex items-center gap-1 px-5 py-2 border-b border-slate-100 shrink-0 overflow-x-auto">
        <Filter size={12} className="text-slate-400 mr-1 shrink-0" />
        {FILTERS.map((filter) => {
          const count =
            filter.id === 'all'
              ? assets.length
              : filter.id === 'figure'
                ? assets.filter((asset) => asset.asset_type === 'figure').length
                : assets.filter((asset) => asset.classification === filter.id).length
          if (count === 0 && filter.id !== 'all') return null
          return (
            <button
              key={filter.id}
              onClick={() => setActiveFilter(filter.id)}
              className={clsx(
                'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition-colors whitespace-nowrap',
                activeFilter === filter.id
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-500 hover:bg-slate-100',
              )}
            >
              {filter.icon}{filter.label}
              <span
                className={clsx(
                  'ml-0.5 text-[10px]',
                  activeFilter === filter.id ? 'opacity-70' : 'text-slate-400',
                )}
              >
                {count}
              </span>
            </button>
          )
        })}
      </div>

      <div className="flex-1 overflow-y-auto bg-slate-50 p-5">
        {filteredAssets.length === 0 ? (
          <div className="h-64 flex flex-col items-center justify-center text-slate-300 gap-2">
            <LayoutGrid size={36} strokeWidth={1} />
            <p className="text-sm">
              {assets.length === 0
                ? 'No elements were extracted from this document.'
                : 'No elements match this filter.'}
            </p>
          </div>
        ) : (
          <>
            <p className="text-[11px] text-slate-400 mb-3">
              {filteredAssets.length} element{filteredAssets.length !== 1 ? 's' : ''}
              {selectedCount > 0 && ` · ${selectedCount} starred`}
            </p>
            <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4">
              {filteredAssets.map((asset) => (
                <AssetCard
                  key={asset.id}
                  asset={asset}
                  onClick={setSelectedAsset}
                  onToggleSelect={handleToggleSelect}
                />
              ))}
            </div>
          </>
        )}
      </div>

      {selectedAsset && (
        <AssetDetailPanel
          asset={selectedAsset}
          assetId={selectedAsset.id}
          projectId={pid}
          paperId={paperIdNum}
          onClose={() => setSelectedAsset(null)}
          onToggleSelect={handleToggleSelect}
        />
      )}
    </div>
  )
}
