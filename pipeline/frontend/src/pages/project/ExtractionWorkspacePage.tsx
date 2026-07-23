import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, CheckCircle2, Circle, Loader2, AlertCircle,
  BarChart3, Table2, Image, Layers, Filter, RefreshCw,
  FileText, Star, ChevronRight, FileType2, LayoutGrid,
  BarChart2, AlignLeft,
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { workspaceApi } from '../../services/api'
import AssetCard from '../../components/AssetCard'
import AssetDetailPanel from '../../components/AssetDetailPanel'
import type { ExtractionAsset, WorkspaceStatus } from '../../types/workspace'

// ─── Pipeline stages ───────────────────────────────────────────────────────────

const PIPELINE_STAGES = [
  { id: 'ingest',   label: 'PDF Ingestion',           minProgress: 0,  doneAt: 5 },
  { id: 'ocr',      label: 'OCR',                     minProgress: 5,  doneAt: 10 },
  { id: 'layout',   label: 'Layout Analysis',         minProgress: 10, doneAt: 15 },
  { id: 'sections', label: 'Section Parsing',         minProgress: 15, doneAt: 25 },
  { id: 'tables',   label: 'Native Table Extraction', minProgress: 25, doneAt: 35 },
  { id: 'figures',  label: 'Figure Extraction',       minProgress: 35, doneAt: 50 },
  { id: 'captions', label: 'Caption Linking',         minProgress: 50, doneAt: 65 },
  { id: 'coords',   label: 'Page Coordinates',        minProgress: 65, doneAt: 85 },
  { id: 'export',   label: 'Artifact Export',         minProgress: 85, doneAt: 100 },
]

type StageState = 'done' | 'active' | 'pending'

function stageState(progress: number, stage: typeof PIPELINE_STAGES[0]): StageState {
  if (progress >= stage.doneAt) return 'done'
  if (progress >= stage.minProgress) return 'active'
  return 'pending'
}

// ─── Filter tabs ───────────────────────────────────────────────────────────────

const FILTERS = [
  { id: 'all',          label: 'All',     icon: <Layers size={12} /> },
  { id: 'chart',        label: 'Charts',  icon: <BarChart2 size={12} /> },
  { id: 'native_table', label: 'Tables',  icon: <Table2 size={12} /> },
  { id: 'figure',       label: 'Figures', icon: <Image size={12} /> },
  { id: 'photograph',   label: 'Photos',  icon: <Image size={12} /> },
  { id: 'diagram',      label: 'Diagrams',icon: <Image size={12} /> },
]

// ─── Component ─────────────────────────────────────────────────────────────────

export default function ExtractionWorkspacePage() {
  const { projectId, paperId } = useParams<{ projectId: string; paperId: string }>()
  const pid        = Number(projectId)
  const paperIdNum = Number(paperId)
  const navigate   = useNavigate()

  const [status, setStatus]               = useState<WorkspaceStatus | null>(null)
  const [assets, setAssets]               = useState<ExtractionAsset[]>([])
  const [paperName, setPaperName]         = useState('')
  const [activeFilter, setActiveFilter]   = useState('all')
  const [selectedAsset, setSelectedAsset] = useState<ExtractionAsset | null>(null)
  const [starting, setStarting]           = useState(false)
  const [previewUrl, setPreviewUrl]       = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const isRunning = status?.status === 'running' || status?.status === 'queued'
  const isDone    = status?.status === 'completed'
  const isFailed  = status?.status === 'failed'

  // ── Fetch assets ────────────────────────────────────────────────────────────
  const fetchAssets = useCallback(async () => {
    try {
      const res = await workspaceApi.listAssets(pid, paperIdNum, { limit: 200 })
      setAssets(res.items)
      const withPage = (res.items as ExtractionAsset[]).find((a) => a.has_page_image)
      if (withPage && !previewUrl) {
        setPreviewUrl(workspaceApi.pageImageUrl(pid, paperIdNum, withPage.id))
      }
    } catch { /* silent */ }
  }, [pid, paperIdNum])

  // ── Poll status ─────────────────────────────────────────────────────────────
  const pollStatus = useCallback(async () => {
    try {
      const s: WorkspaceStatus = await workspaceApi.status(pid, paperIdNum)
      setStatus(s)
      if (s.status === 'running' || s.status === 'queued') fetchAssets()
      else if (s.status === 'completed') {
        fetchAssets()
        if (pollRef.current) clearInterval(pollRef.current)
      } else if (s.status === 'failed') {
        if (pollRef.current) clearInterval(pollRef.current)
        toast.error('Extraction failed: ' + (s.error ?? 'unknown error'))
      }
    } catch { /* silent */ }
  }, [pid, paperIdNum, fetchAssets])

  // ── Init ────────────────────────────────────────────────────────────────────
  useEffect(() => {
    const init = async () => {
      const s: WorkspaceStatus = await workspaceApi.status(pid, paperIdNum)
      setStatus(s)
      if (s.status === 'not_started') {
        setStarting(true)
        try {
          const res = await workspaceApi.start(pid, paperIdNum)
          setPaperName(res.paper?.filename ?? '')
          const fresh = await workspaceApi.status(pid, paperIdNum)
          setStatus(fresh)
        } catch (e: any) {
          toast.error(e.response?.data?.detail ?? 'Failed to start extraction')
        } finally {
          setStarting(false)
        }
      } else if (s.status === 'completed') {
        fetchAssets(); return
      } else if (s.status === 'running' || s.status === 'queued') {
        fetchAssets()
      }
      pollRef.current = setInterval(pollStatus, 2500)
    }
    init()
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [pid, paperIdNum])

  useEffect(() => {
    if (isRunning && !pollRef.current) pollRef.current = setInterval(pollStatus, 2500)
  }, [isRunning, pollStatus])

  const handleToggleSelect = async (asset: ExtractionAsset, val: boolean) => {
    try {
      const updated = await workspaceApi.patchAsset(pid, paperIdNum, asset.id, { selected_for_llm: val })
      setAssets((prev) => prev.map((a) => a.id === asset.id ? { ...a, selected_for_llm: updated.selected_for_llm } : a))
      if (selectedAsset?.id === asset.id)
        setSelectedAsset((prev) => prev ? { ...prev, selected_for_llm: updated.selected_for_llm } : prev)
    } catch {
      toast.error('Failed to update selection')
    }
  }

  const filteredAssets = assets.filter((a) => {
    if (activeFilter === 'all') return true
    if (activeFilter === 'figure') return a.asset_type === 'figure'
    return a.classification === activeFilter
  })

  const selectedCount = assets.filter((a) => a.selected_for_llm).length
  const progress  = status?.progress ?? 0
  const nFigures  = assets.filter((a) => a.asset_type === 'figure').length
  const nTables   = assets.filter((a) => a.asset_type === 'native_table').length
  const nCharts   = assets.filter((a) => a.classification === 'chart').length

  // ─── Processing view ───────────────────────────────────────────────────────
  if (!isDone && !isFailed && (isRunning || starting || !status)) {
    return (
      <div className="flex flex-col h-full bg-white">

        {/* Info bar */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-200 shrink-0">
          <Link to={`/projects/${pid}/upload`} className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg">
            <ArrowLeft size={16} />
          </Link>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-bold text-slate-900 truncate">{paperName || `Paper ${paperIdNum}`}</h1>
              <span className="flex items-center gap-1 text-[10px] font-semibold text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-100">
                <Loader2 size={9} className="animate-spin" /> Running
              </span>
            </div>
            {status?.current_step && (
              <p className="text-[11px] text-slate-400 mt-0.5 truncate">{status.current_step}</p>
            )}
          </div>
          <div className="shrink-0 flex items-center gap-3">
            <span className="text-sm font-bold text-slate-700">{progress}%</span>
            <div className="w-28 h-2 bg-slate-100 rounded-full overflow-hidden">
              <div className="h-full bg-blue-500 rounded-full transition-all duration-700" style={{ width: `${progress}%` }} />
            </div>
          </div>
        </div>

        {/* Stage track */}
        <div className="flex items-center gap-0 px-5 py-2.5 border-b border-slate-100 bg-slate-50 shrink-0 overflow-x-auto">
          {PIPELINE_STAGES.map((stage, i) => {
            const state = stageState(progress, stage)
            return (
              <div key={stage.id} className="flex items-center shrink-0">
                <div className={clsx(
                  'flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[10px] font-medium transition-all',
                  state === 'done'   ? 'bg-emerald-50 text-emerald-700' :
                  state === 'active' ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-200' :
                                       'bg-white text-slate-300 border border-slate-100',
                )}>
                  {state === 'done'   ? <CheckCircle2 size={10} className="text-emerald-500" /> :
                   state === 'active' ? <Loader2 size={10} className="animate-spin text-blue-500" /> :
                                        <Circle size={10} className="text-slate-200" />}
                  {stage.label}
                </div>
                {i < PIPELINE_STAGES.length - 1 && <ChevronRight size={10} className="text-slate-200 mx-0.5" />}
              </div>
            )
          })}
        </div>

        {/* 3-column body */}
        <div className="flex flex-1 overflow-hidden">

          {/* Left: steps + counts */}
          <div className="w-56 shrink-0 border-r border-slate-200 flex flex-col overflow-y-auto">
            <div className="px-4 py-3">
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-3">Pipeline Steps</p>
              <div className="space-y-2">
                {PIPELINE_STAGES.map((stage) => {
                  const state = stageState(progress, stage)
                  return (
                    <div key={stage.id} className="flex items-center gap-2">
                      {state === 'done'   ? <CheckCircle2 size={13} className="text-emerald-500 shrink-0" /> :
                       state === 'active' ? <Loader2 size={13} className="text-blue-500 animate-spin shrink-0" /> :
                                            <Circle size={13} className="text-slate-200 shrink-0" />}
                      <span className={clsx('text-[11px] leading-snug',
                        state === 'done'   ? 'text-slate-600' :
                        state === 'active' ? 'text-blue-700 font-semibold' :
                                             'text-slate-300',
                      )}>{stage.label}</span>
                    </div>
                  )
                })}
              </div>
            </div>

            {assets.length > 0 && (
              <div className="px-4 py-3 border-t border-slate-100 mt-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-3">Extracted</p>
                <div className="space-y-2">
                  {[
                    { label: 'Figures',  count: nFigures, Icon: Image,    color: 'text-violet-500' },
                    { label: 'Charts',   count: nCharts,  Icon: BarChart3, color: 'text-emerald-500' },
                    { label: 'Tables',   count: nTables,  Icon: Table2,   color: 'text-blue-500' },
                  ].map(({ label, count, Icon, color }) => (
                    <div key={label} className="flex items-center justify-between py-1 border-b border-slate-50 last:border-0">
                      <div className="flex items-center gap-1.5">
                        <Icon size={12} className={color} />
                        <span className="text-[11px] text-slate-600">{label}</span>
                      </div>
                      <span className="text-sm font-bold text-slate-800">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Center: document preview */}
          <div className="flex-1 flex flex-col bg-slate-100 overflow-hidden">
            <div className="px-4 py-2 border-b border-slate-200 bg-white flex items-center justify-between shrink-0">
              <span className="text-[11px] font-semibold text-slate-500 flex items-center gap-1.5">
                <FileType2 size={12} className="text-slate-400" />
                Document Preview
              </span>
              <span className="text-[10px] text-slate-400">
                {assets.length > 0 ? `${assets.length} elements detected` : 'Parsing…'}
              </span>
            </div>
            <div className="flex-1 overflow-auto flex items-start justify-center p-6">
              {previewUrl ? (
                <img
                  src={previewUrl}
                  alt="Page preview"
                  className="max-w-full rounded-xl border border-slate-300 shadow-lg bg-white"
                />
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-slate-300 gap-4 py-20 w-full">
                  <FileText size={44} strokeWidth={1} />
                  <div className="text-center">
                    <p className="text-sm font-medium text-slate-400">
                      {progress < 25 ? 'Parsing document structure…' : 'Extracting visual elements…'}
                    </p>
                    <p className="text-xs text-slate-300 mt-1">Preview will appear once pages are rendered</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right: live mini-gallery */}
          <div className="w-64 shrink-0 border-l border-slate-200 bg-white flex flex-col overflow-hidden">
            <div className="px-4 py-2 border-b border-slate-200 flex items-center justify-between shrink-0">
              <span className="text-[11px] font-semibold text-slate-500 flex items-center gap-1.5">
                <LayoutGrid size={11} className="text-slate-400" />
                Live Gallery
              </span>
              {assets.length > 0 && <span className="text-[10px] text-slate-400">{assets.length}</span>}
            </div>
            <div className="flex-1 overflow-y-auto p-2.5">
              {assets.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-slate-200 gap-2 py-10">
                  <LayoutGrid size={28} strokeWidth={1} />
                  <p className="text-[11px] text-center text-slate-300">Elements appear here as they are extracted</p>
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {assets.map((asset) => (
                    <AssetCard
                      key={asset.id}
                      asset={asset}
                      projectId={pid}
                      paperId={paperIdNum}
                      onClick={setSelectedAsset}
                      onToggleSelect={handleToggleSelect}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ─── Failure view ──────────────────────────────────────────────────────────
  if (isFailed) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-5">
        <div className="w-14 h-14 bg-red-50 rounded-full flex items-center justify-center">
          <AlertCircle size={24} className="text-red-400" />
        </div>
        <div className="text-center">
          <h2 className="text-base font-bold text-slate-700">Extraction failed</h2>
          <p className="text-sm text-red-500 mt-1 max-w-md">{status?.error ?? 'Unknown error'}</p>
        </div>
        <div className="flex gap-3">
          <Link to={`/projects/${pid}/upload`} className="btn-secondary text-sm">
            <ArrowLeft size={13} /> Back
          </Link>
          <button
            onClick={async () => {
              setStarting(true)
              try {
                await workspaceApi.start(pid, paperIdNum)
                const s = await workspaceApi.status(pid, paperIdNum)
                setStatus(s)
                pollRef.current = setInterval(pollStatus, 2500)
              } finally { setStarting(false) }
            }}
            className="btn-primary text-sm"
          >
            <RefreshCw size={13} /> Retry
          </button>
        </div>
      </div>
    )
  }

  // ─── Explorer view (completed) ─────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full bg-white">

      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-200 shrink-0">
        <Link to={`/projects/${pid}/upload`} className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg">
          <ArrowLeft size={16} />
        </Link>
        <div className="flex-1 min-w-0">
          <h1 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            Extraction Workspace
            <span className="text-[10px] font-semibold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-100">
              Complete
            </span>
          </h1>
          {status?.result && (
            <p className="text-[11px] text-slate-400 mt-0.5">
              {status.result.page_count} pages · {status.result.figures} figures
              {status.result.chart_conversion_available === false
                ? ' (charts: PP unavailable)'
                : ` (${status.result.charts} charts)`}
              {' '}· {status.result.native_tables} tables
              {status.result.decorative_excluded
                ? ` · ${status.result.decorative_excluded} decorative excluded`
                : ''}
            </p>
          )}
        </div>
        <Link
          to={`/projects/${pid}/papers/${paperIdNum}/chart2table`}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 text-slate-600 rounded-lg text-xs font-semibold hover:bg-slate-200 transition-colors"
        >
          <BarChart3 size={12} />
          Charts
        </Link>
        {selectedCount > 0 && (
          <button
            onClick={() => navigate(`/projects/${pid}/validation?paperId=${paperIdNum}`)}
            className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-semibold hover:bg-blue-700 transition-colors"
          >
            <Star size={12} />
            {selectedCount} for LLM
            <ChevronRight size={11} />
          </button>
        )}
      </div>

      {/* Completed stage track */}
      <div className="flex items-center gap-0 px-5 py-2 border-b border-slate-100 bg-slate-50 shrink-0 overflow-x-auto">
        {PIPELINE_STAGES.map((stage, i) => (
          <div key={stage.id} className="flex items-center shrink-0">
            <div className="flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium bg-emerald-50 text-emerald-600">
              <CheckCircle2 size={9} /> {stage.label}
            </div>
            {i < PIPELINE_STAGES.length - 1 && <ChevronRight size={9} className="text-slate-300 mx-0.5" />}
          </div>
        ))}
      </div>

      {/* Filter tabs */}
      <div className="flex items-center gap-1 px-5 py-2 border-b border-slate-100 shrink-0 overflow-x-auto">
        <Filter size={12} className="text-slate-400 mr-1 shrink-0" />
        {FILTERS.map((f) => {
          const count = f.id === 'all'
            ? assets.length
            : f.id === 'figure'
            ? assets.filter((a) => a.asset_type === 'figure').length
            : assets.filter((a) => a.classification === f.id).length
          if (count === 0 && f.id !== 'all') return null
          return (
            <button
              key={f.id}
              onClick={() => setActiveFilter(f.id)}
              className={clsx(
                'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition-colors whitespace-nowrap',
                activeFilter === f.id ? 'bg-blue-600 text-white' : 'text-slate-500 hover:bg-slate-100',
              )}
            >
              {f.icon}{f.label}
              <span className={clsx('ml-0.5 text-[10px]', activeFilter === f.id ? 'opacity-70' : 'text-slate-400')}>{count}</span>
            </button>
          )
        })}
      </div>

      {/* Gallery */}
      <div className="flex-1 overflow-y-auto bg-slate-50 p-5">
        {filteredAssets.length === 0 ? (
          <div className="h-64 flex flex-col items-center justify-center text-slate-300 gap-2">
            <Layers size={36} strokeWidth={1} />
            <p className="text-sm">No elements match this filter.</p>
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
                  projectId={pid}
                  paperId={paperIdNum}
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
          projectId={pid}
          paperId={paperIdNum}
          onClose={() => setSelectedAsset(null)}
          onToggleSelect={handleToggleSelect}
        />
      )}
    </div>
  )
}
