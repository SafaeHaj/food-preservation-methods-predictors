/**
 * Extracted Data — everything the pipeline pulled out of this project's PDFs, in one place.
 *
 * The per-paper workspace (`papers/:paperId/workspace`) is unchanged and still owns the
 * work: starting a parse, starring assets, sending a selection to the LLM. What was missing
 * was a way to see across papers — the only route in was a "Workspace" link on the project
 * overview, one paper at a time, so "what has this project actually extracted?" had no
 * answer short of opening each paper in turn.
 *
 * This reads `GET /projects/{id}/assets`, which the API layer has exposed since the
 * workspace refactor and which nothing called until now.
 */

import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  BarChart2, FileText, Filter, Image, LayoutGrid, Loader2, Microscope, Star, Table2,
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

import { usePapers } from '../../api/papers'
import { useProjectAssets, useUpdateAsset } from '../../api/workspace'
import { errorMessage } from '../../api/errors'
import AssetCard from '../../components/AssetCard'
import AssetDetailPanel from '../../components/AssetDetailPanel'
import type { ExtractionAsset } from '../../types/workspace'

const FILTERS = [
  { id: 'all', label: 'All', icon: <LayoutGrid size={12} /> },
  { id: 'chart', label: 'Charts', icon: <BarChart2 size={12} /> },
  { id: 'native_table', label: 'Tables', icon: <Table2 size={12} /> },
  { id: 'figure', label: 'Figures', icon: <Image size={12} /> },
  { id: 'photograph', label: 'Photos', icon: <Image size={12} /> },
  { id: 'diagram', label: 'Diagrams', icon: <Image size={12} /> },
]

function AssetGrid({
  projectId, assets, paperName, onSelect,
}: {
  projectId: number
  assets: ExtractionAsset[]
  paperName: (paperId: number) => string
  onSelect: (asset: ExtractionAsset) => void
}) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4">
      {assets.map((asset) => (
        <div key={asset.id} className="space-y-1">
          <p className="text-[10px] text-slate-400 truncate flex items-center gap-1">
            <FileText size={9} className="shrink-0" /> {paperName(asset.paper_id)}
          </p>
          <StarrableCard projectId={projectId} asset={asset} onSelect={onSelect} />
        </div>
      ))}
    </div>
  )
}

function StarrableCard({
  projectId, asset, onSelect,
}: {
  projectId: number
  asset: ExtractionAsset
  onSelect: (asset: ExtractionAsset) => void
}) {
  const update = useUpdateAsset(projectId, asset.paper_id)

  const handleToggle = (target: ExtractionAsset, value: boolean) =>
    update
      .mutateAsync({ assetId: target.id, selected_for_llm: value })
      .catch((error) => toast.error(errorMessage(error, 'Could not update the selection')))

  return <AssetCard asset={asset} onClick={onSelect} onToggleSelect={handleToggle} />
}

export default function ExtractedDataPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const pid = Number(projectId)
  const navigate = useNavigate()

  const [activeFilter, setActiveFilter] = useState('all')
  const [paperFilter, setPaperFilter] = useState<number | 'all'>('all')
  const [selectedAsset, setSelectedAsset] = useState<ExtractionAsset | null>(null)

  const { data: papers = [] } = usePapers(pid)
  const { data: page, isLoading } = useProjectAssets(pid)
  const assets = useMemo(() => page?.items ?? [], [page])

  const paperName = useMemo(() => {
    const map = new Map(papers.map((p) => [p.id, p.original_name]))
    return (id: number) => map.get(id) ?? `Paper ${id}`
  }, [papers])

  const visible = useMemo(
    () =>
      assets.filter((asset) => {
        if (paperFilter !== 'all' && asset.paper_id !== paperFilter) return false
        if (activeFilter === 'all') return true
        if (activeFilter === 'figure') return asset.asset_type === 'figure'
        return asset.classification === activeFilter
      }),
    [assets, activeFilter, paperFilter],
  )

  const starred = visible.filter((asset) => asset.selected_for_llm).length
  const unanalysed = papers.filter((paper) => paper.status === 'uploaded').length

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="page-title">Extracted Data</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Every figure, chart and table the pipeline pulled out of this project's papers.
            Open one to see its context, or a paper to re-run and curate it.
          </p>
        </div>
        {papers.length > 0 && (
          <select
            value={paperFilter}
            onChange={(e) =>
              setPaperFilter(e.target.value === 'all' ? 'all' : Number(e.target.value))
            }
            className="text-xs border border-slate-200 rounded-lg px-3 py-1.5 bg-white text-slate-700 max-w-xs"
          >
            <option value="all">All papers</option>
            {papers.map((paper) => (
              <option key={paper.id} value={paper.id}>{paper.original_name}</option>
            ))}
          </select>
        )}
      </div>

      {unanalysed > 0 && (
        <div className="flex items-center gap-2 text-[11px] text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
          <FileText size={12} className="shrink-0" />
          {unanalysed} paper{unanalysed !== 1 ? 's have' : ' has'} not been analysed yet — open
          {unanalysed !== 1 ? ' one' : ' it'} from the list below to run the pipeline.
        </div>
      )}

      <div className="flex items-center gap-1 border-b border-slate-100 pb-2 overflow-x-auto">
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

      {isLoading ? (
        <div className="flex items-center gap-2 text-slate-400 py-8 text-sm">
          <Loader2 size={14} className="animate-spin" /> Loading extracted elements…
        </div>
      ) : visible.length === 0 ? (
        <div className="text-center py-16 text-slate-300">
          <LayoutGrid size={40} strokeWidth={1} className="mx-auto mb-3" />
          <p className="text-sm text-slate-400">
            {assets.length === 0
              ? 'Nothing has been extracted yet. Analyse a paper to fill this in.'
              : 'No elements match these filters.'}
          </p>
        </div>
      ) : (
        <>
          <p className="text-[11px] text-slate-400">
            {visible.length} element{visible.length !== 1 ? 's' : ''}
            {starred > 0 && (
              <> · <Star size={9} className="inline text-amber-500" /> {starred} starred for the LLM</>
            )}
            {page && page.total > assets.length && (
              <> · showing the first {assets.length} of {page.total}</>
            )}
          </p>
          <AssetGrid
            projectId={pid}
            assets={visible}
            paperName={paperName}
            onSelect={setSelectedAsset}
          />
        </>
      )}

      {/* ── Papers, as the way into the per-paper workspace ───────────────────── */}
      {papers.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100">
            <h2 className="section-title">Papers</h2>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Open a paper's workspace to re-run the pipeline or curate what goes to the LLM.
            </p>
          </div>
          <div className="divide-y divide-slate-100">
            {papers.map((paper) => (
              <button
                key={paper.id}
                onClick={() => navigate(`/projects/${pid}/papers/${paper.id}/workspace`)}
                className="w-full flex items-center gap-3 px-5 py-3 text-left hover:bg-slate-50 transition-colors"
              >
                <FileText size={14} className="text-slate-300 shrink-0" />
                <span className="flex-1 min-w-0 text-sm text-slate-800 truncate">
                  {paper.original_name}
                </span>
                <span className="text-[11px] text-slate-400 shrink-0">
                  {paper.asset_count} element{paper.asset_count !== 1 ? 's' : ''}
                  {paper.experiment_count > 0 && (
                    <> · {paper.experiment_count} experiment{paper.experiment_count !== 1 ? 's' : ''}</>
                  )}
                </span>
                <Microscope size={13} className="text-blue-500 shrink-0" />
              </button>
            ))}
          </div>
        </div>
      )}

      {selectedAsset && (
        <AssetDetailPanel
          asset={selectedAsset}
          assetId={selectedAsset.id}
          projectId={pid}
          paperId={selectedAsset.paper_id}
          onClose={() => setSelectedAsset(null)}
        />
      )}
    </div>
  )
}
