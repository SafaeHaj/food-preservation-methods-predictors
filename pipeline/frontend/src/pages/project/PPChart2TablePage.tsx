import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  BarChart3, Table2, Image, FileSpreadsheet, CheckCircle2,
  XCircle, AlertTriangle, Download, ChevronDown, ChevronUp,
  Loader2, InboxIcon, FileText, Info, ShieldCheck,
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { workspaceApi } from '../../services/api'
import type { ExtractionAsset, AssetDetail, ContextLink } from '../../types/workspace'

// ─── Status badge helpers ─────────────────────────────────────────────────────

type StatusKey = 'valid' | 'review' | 'not_chart' | 'table' | 'unknown'

function assetStatus(a: ExtractionAsset): StatusKey {
  if (a.asset_type === 'native_table') return 'table'
  if (a.conversion_status === 'complete') return 'valid'
  if (a.classification === 'photograph' || a.classification === 'diagram') return 'not_chart'
  if (a.conversion_status === 'failed' || a.conversion_status === 'pending') return 'review'
  return 'unknown'
}

const STATUS_META: Record<StatusKey, { label: string; bg: string; text: string }> = {
  valid:     { label: 'Probably Valid',  bg: 'bg-emerald-100', text: 'text-emerald-700' },
  review:    { label: 'Needs Review',    bg: 'bg-amber-100',   text: 'text-amber-700' },
  not_chart: { label: 'Not a Chart',     bg: 'bg-red-100',     text: 'text-red-600' },
  table:     { label: 'Native Table',    bg: 'bg-blue-100',    text: 'text-blue-700' },
  unknown:   { label: 'Unclassified',    bg: 'bg-slate-100',   text: 'text-slate-500' },
}

// ─── Context link type labels ─────────────────────────────────────────────────

const LINK_LABELS: Record<string, { label: string; color: string }> = {
  caption:                   { label: 'Caption',       color: 'bg-blue-50 text-blue-700' },
  neighbor_before:           { label: 'Before',        color: 'bg-slate-100 text-slate-600' },
  neighbor_after:            { label: 'After',         color: 'bg-slate-100 text-slate-600' },
  explicit_figure_reference: { label: 'Explicit Ref',  color: 'bg-emerald-50 text-emerald-700' },
  keyword_match:             { label: 'Keyword',       color: 'bg-violet-50 text-violet-600' },
  same_section:              { label: 'Same Section',  color: 'bg-amber-50 text-amber-700' },
}

// ─── CSV preview ──────────────────────────────────────────────────────────────

function CsvTable({ projectId, paperId, assetId }: { projectId: number; paperId: number; assetId: number }) {
  const [rows, setRows] = useState<string[][]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState(false)

  useEffect(() => {
    setLoading(true)
    setErr(false)
    fetch(workspaceApi.csvUrl(projectId, paperId, assetId))
      .then((r) => {
        if (!r.ok) throw new Error('failed')
        return r.text()
      })
      .then((txt) => {
        const lines = txt.trim().split('\n').slice(0, 15)
        setRows(lines.map((l) => l.split(',').map((c) => c.trim().replace(/^"|"$/g, ''))))
        setLoading(false)
      })
      .catch(() => { setErr(true); setLoading(false) })
  }, [projectId, paperId, assetId])

  if (loading) return <div className="flex items-center gap-2 text-sm text-slate-400 py-4"><Loader2 size={14} className="animate-spin" />Loading CSV…</div>
  if (err || !rows.length) return <p className="text-sm text-slate-400 italic py-4">No CSV data available.</p>

  const [header, ...data] = rows
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="text-[11px] w-full">
        <thead>
          <tr className="bg-slate-50 border-b border-slate-200">
            {header.map((h, i) => (
              <th key={i} className="px-2.5 py-2 text-left font-semibold text-slate-600 whitespace-nowrap">{h || '—'}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, ri) => (
            <tr key={ri} className="border-b border-slate-100 last:border-0 even:bg-slate-50/40">
              {row.map((cell, ci) => (
                <td key={ci} className="px-2.5 py-1.5 text-slate-700 whitespace-nowrap">{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ─── Validation checks ────────────────────────────────────────────────────────

function ValidationChecks({ asset, detail }: { asset: ExtractionAsset; detail: AssetDetail | null }) {
  const checks = [
    {
      label: 'Figure image extracted',
      pass: asset.has_image,
      warn: false,
    },
    {
      label: 'Page image available',
      pass: asset.has_page_image,
      warn: false,
    },
    {
      label: 'Caption detected',
      pass: !!asset.caption,
      warn: !asset.caption,
    },
    {
      label: 'CSV conversion successful',
      pass: asset.conversion_status === 'complete',
      warn: ['pending', 'skipped', 'not_a_chart'].includes(asset.conversion_status ?? ''),
    },
    {
      label: 'Context text linked',
      pass: (detail?.context_links?.length ?? 0) > 0,
      warn: false,
    },
    {
      label: 'Relevance score ≥ 5',
      pass: asset.relevance_score >= 5,
      warn: asset.relevance_score > 0 && asset.relevance_score < 5,
    },
  ]

  return (
    <div className="space-y-1.5">
      {checks.map(({ label, pass, warn }) => (
        <div key={label} className="flex items-center gap-2.5 py-1">
          {pass ? (
            <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
          ) : warn ? (
            <AlertTriangle size={14} className="text-amber-500 shrink-0" />
          ) : (
            <XCircle size={14} className="text-red-400 shrink-0" />
          )}
          <span className={clsx('text-xs', pass ? 'text-slate-600' : warn ? 'text-amber-600' : 'text-slate-400')}>
            {label}
          </span>
        </div>
      ))}
    </div>
  )
}

// ─── Figure list item ─────────────────────────────────────────────────────────

function FigureListItem({
  asset,
  index,
  selected,
  onClick,
}: {
  asset: ExtractionAsset
  index: number
  selected: boolean
  onClick: () => void
}) {
  const status = assetStatus(asset)
  const meta = STATUS_META[status]
  const imgUrl = asset.has_image ? workspaceApi.imageUrl(asset.project_id, asset.paper_id, asset.id) : null
  const typeLabel = asset.asset_type === 'native_table' ? 'Table' : 'Figure'
  const [imgErr, setImgErr] = useState(false)

  return (
    <button
      onClick={onClick}
      className={clsx(
        'w-full text-left flex gap-3 p-3 border-b border-slate-100 transition-all duration-150',
        selected
          ? 'bg-blue-50 border-l-2 border-l-blue-500'
          : 'hover:bg-slate-50 border-l-2 border-l-transparent',
      )}
    >
      {/* Thumbnail */}
      <div className="w-14 h-14 shrink-0 bg-slate-100 rounded-lg overflow-hidden flex items-center justify-center border border-slate-200">
        {imgUrl && !imgErr ? (
          <img
            src={imgUrl}
            alt=""
            className="w-full h-full object-contain"
            onError={() => setImgErr(true)}
          />
        ) : asset.asset_type === 'native_table' ? (
          <Table2 size={22} className="text-slate-300" />
        ) : (
          <Image size={22} className="text-slate-300" />
        )}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 mb-1">
          <span className="text-[11px] font-semibold text-slate-800">
            {typeLabel} {index + 1}
          </span>
          {asset.page_number && (
            <span className="text-[10px] text-slate-400">· p.{asset.page_number}</span>
          )}
        </div>
        <p className="text-[10px] text-slate-500 leading-snug line-clamp-2 mb-1.5">
          {asset.caption ?? 'No caption'}
        </p>
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className={clsx('text-[9px] font-semibold px-1.5 py-0.5 rounded-full', meta.bg, meta.text)}>
            {meta.label}
          </span>
          {asset.relevance_score > 0 && (
            <span className="text-[9px] text-slate-400 font-medium">
              Score {asset.relevance_score.toFixed(1)}
            </span>
          )}
        </div>
      </div>
    </button>
  )
}

// ─── Detail tabs ─────────────────────────────────────────────────────────────

type Tab = 'figure' | 'csv' | 'caption' | 'context'

const TABS: { id: Tab; label: string }[] = [
  { id: 'figure',  label: 'Original Figure' },
  { id: 'csv',     label: 'Generated CSV' },
  { id: 'caption', label: 'Caption' },
  { id: 'context', label: 'Nearby Text' },
]

// ─── Right metadata panel ─────────────────────────────────────────────────────

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 py-1 border-b border-slate-100 last:border-0">
      <span className="w-28 shrink-0 text-[11px] text-slate-400">{label}</span>
      <span className="text-[11px] text-slate-700 font-medium">{value ?? '—'}</span>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function PPChart2TablePage() {
  const { projectId, paperId } = useParams<{ projectId: string; paperId: string }>()
  const pid    = Number(projectId)
  const paperIdNum = Number(paperId)

  const [assets, setAssets] = useState<ExtractionAsset[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<ExtractionAsset | null>(null)
  const [detail, setDetail] = useState<AssetDetail | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('figure')
  const [expandedLinks, setExpandedLinks] = useState<Record<number, boolean>>({})
  const [imgErr, setImgErr] = useState(false)
  const [ppHealth, setPpHealth] = useState<{ available: boolean; last_error: string | null } | null>(null)

  // Fetch PP-Chart2Table health status
  useEffect(() => {
    fetch('/api/chart2table/health')
      .then((r) => r.json())
      .then(setPpHealth)
      .catch(() => null)
  }, [])

  // Fetch figures for THIS paper only — never project-wide
  const fetchAssets = useCallback(async () => {
    if (!paperIdNum) return
    try {
      const res = await workspaceApi.listAssets(pid, paperIdNum, { limit: 500 })
      setAssets(res.items)
      if (res.items.length > 0 && !selected) {
        setSelected(res.items[0])
      }
    } catch {
      toast.error('Failed to load figures')
    } finally {
      setLoading(false)
    }
  }, [pid, paperIdNum])

  useEffect(() => { fetchAssets() }, [fetchAssets])

  // Load detail when selection changes
  useEffect(() => {
    if (!selected) { setDetail(null); return }
    setDetail(null)
    setImgErr(false)
    setActiveTab('figure')
    workspaceApi.getAsset(pid, paperIdNum, selected.id)
      .then(setDetail)
      .catch(() => null)
  }, [selected?.id, paperIdNum])

  const figures = assets.filter((a) => a.asset_type === 'figure')
  const tables  = assets.filter((a) => a.asset_type === 'native_table')

  const figureUrl = selected?.has_image
    ? workspaceApi.imageUrl(pid, paperIdNum, selected.id)
    : null
  const pageUrl = selected?.has_page_image
    ? workspaceApi.pageImageUrl(pid, paperIdNum, selected.id)
    : null

  const typeLabel = selected?.asset_type === 'native_table' ? 'Table' : 'Figure'
  const selectedIndex = assets.indexOf(selected as ExtractionAsset)

  // No paper in route → show selection prompt
  if (!paperIdNum) {
    return (
      <div className="flex flex-col h-full items-center justify-center text-slate-300 gap-4">
        <InboxIcon size={48} strokeWidth={1} />
        <div className="text-center">
          <p className="text-base font-semibold text-slate-500">No paper selected</p>
          <p className="text-sm text-slate-400 mt-1">
            Open a paper's Extraction Workspace and navigate to Charts from there.
          </p>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-slate-400 gap-3">
        <Loader2 size={20} className="animate-spin" />
        <span className="text-sm">Loading figures…</span>
      </div>
    )
  }

  if (assets.length === 0) {
    return (
      <div className="flex flex-col h-full items-center justify-center text-slate-300 gap-4">
        <InboxIcon size={48} strokeWidth={1} />
        <div className="text-center">
          <p className="text-base font-semibold text-slate-500">No extracted figures yet</p>
          <p className="text-sm text-slate-400 mt-1">
            Upload a PDF and run the Docling extraction first.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-hidden bg-white">

      {/* ── PP-Chart2Table health banner ───────────────────────────── */}
      {ppHealth && !ppHealth.available && (
        <div className="flex items-center gap-2 px-4 py-2 bg-amber-50 border-b border-amber-200 shrink-0">
          <AlertTriangle size={14} className="text-amber-500 shrink-0" />
          <p className="text-xs text-amber-700">
            <span className="font-semibold">PP-Chart2Table unavailable</span>
            {ppHealth.last_error ? ` — ${ppHealth.last_error}` : ' — PaddleOCR not installed in this environment.'}
            {' '}Chart images cannot be digitized; native tables and text evidence are still available.
          </p>
        </div>
      )}
      {ppHealth?.available && (
        <div className="flex items-center gap-2 px-4 py-2 bg-emerald-50 border-b border-emerald-100 shrink-0">
          <CheckCircle2 size={13} className="text-emerald-500 shrink-0" />
          <p className="text-xs text-emerald-700 font-medium">PP-Chart2Table model loaded and ready.</p>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">

      {/* ── Left: Figure list ──────────────────────────────────────── */}
      <div className="w-72 shrink-0 border-r border-slate-200 flex flex-col h-full">
        {/* Header */}
        <div className="px-4 py-3 border-b border-slate-200 shrink-0">
          <h2 className="text-sm font-bold text-slate-800">Extracted Figures</h2>
          <p className="text-[11px] text-slate-400 mt-0.5">
            {figures.length} figures · {tables.length} tables
          </p>
        </div>

        {/* Filter tabs */}
        <div className="flex gap-1 px-3 py-2 border-b border-slate-100 shrink-0">
          <span className="text-[10px] font-semibold text-slate-400 mr-1 self-center">Show:</span>
          {[
            { label: `All (${assets.length})`, filter: 'all' },
            { label: `Figures (${figures.length})`, filter: 'figure' },
            { label: `Tables (${tables.length})`, filter: 'table' },
          ].map(({ label, filter }) => (
            <button
              key={filter}
              className="text-[10px] px-2 py-1 rounded-md bg-slate-100 text-slate-600 hover:bg-slate-200 transition-colors"
            >
              {label}
            </button>
          ))}
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto">
          {assets.map((asset, i) => (
            <FigureListItem
              key={asset.id}
              asset={asset}
              index={i}
              selected={selected?.id === asset.id}
              onClick={() => setSelected(asset)}
            />
          ))}
        </div>
      </div>

      {/* ── Center: Figure detail ──────────────────────────────────── */}
      <div className="flex-1 min-w-0 flex flex-col h-full border-r border-slate-200">
        {selected ? (
          <>
            {/* Detail header */}
            <div className="px-5 py-3.5 border-b border-slate-200 shrink-0 bg-slate-50">
              <h2 className="text-sm font-bold text-slate-800 leading-snug">
                {typeLabel} {selectedIndex + 1}
                {selected.caption ? ': ' + selected.caption.slice(0, 80) + (selected.caption.length > 80 ? '…' : '') : ''}
              </h2>
              <div className="flex items-center gap-3 mt-1">
                {selected.page_number && (
                  <span className="text-[11px] text-slate-400">Page {selected.page_number}</span>
                )}
                {selected.section_name && (
                  <span className="text-[11px] text-slate-400">· {selected.section_name}</span>
                )}
                <span className={clsx(
                  'text-[10px] font-semibold px-2 py-0.5 rounded-full',
                  STATUS_META[assetStatus(selected)].bg,
                  STATUS_META[assetStatus(selected)].text,
                )}>
                  {STATUS_META[assetStatus(selected)].label}
                </span>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex gap-0 border-b border-slate-200 shrink-0 px-4">
              {TABS.map(({ id, label }) => (
                <button
                  key={id}
                  onClick={() => setActiveTab(id)}
                  className={clsx(
                    'px-4 py-2.5 text-xs font-medium border-b-2 transition-colors -mb-px',
                    activeTab === id
                      ? 'border-blue-600 text-blue-700'
                      : 'border-transparent text-slate-500 hover:text-slate-700',
                  )}
                >
                  {label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-y-auto p-5">
              {activeTab === 'figure' && (
                <div className="flex flex-col items-center gap-4">
                  {figureUrl && !imgErr ? (
                    <img
                      src={figureUrl}
                      alt={selected.caption ?? ''}
                      className="max-w-full rounded-xl border border-slate-200 shadow-sm object-contain bg-slate-50"
                      onError={() => setImgErr(true)}
                    />
                  ) : pageUrl ? (
                    <img
                      src={pageUrl}
                      alt="Page preview"
                      className="max-w-full rounded-xl border border-slate-200 shadow-sm object-contain bg-slate-50"
                    />
                  ) : (
                    <div className="w-full h-64 bg-slate-50 border border-slate-200 rounded-xl flex flex-col items-center justify-center text-slate-300 gap-3">
                      <Image size={40} strokeWidth={1} />
                      <p className="text-sm">No image available</p>
                    </div>
                  )}

                  {/* Metadata grid */}
                  <div className="w-full bg-slate-50 border border-slate-200 rounded-xl p-4">
                    <h3 className="text-[11px] font-bold uppercase tracking-widest text-slate-400 mb-3">Figure Metadata</h3>
                    <MetaRow label="Figure Type" value={selected.asset_type === 'native_table' ? 'Native Table' : 'Extracted Figure'} />
                    <MetaRow label="Classification" value={selected.classification?.replace('_', ' ')} />
                    <MetaRow label="Page" value={selected.page_number} />
                    <MetaRow label="Section" value={selected.section_name} />
                    <MetaRow label="Relevance Score" value={`${(selected.relevance_score ?? 0).toFixed(1)} / 10`} />
                    <MetaRow label="Conversion Status" value={selected.conversion_status ?? 'N/A'} />
                    {selected.csv_rows != null && (
                      <MetaRow label="CSV Dimensions" value={`${selected.csv_rows} rows × ${selected.csv_cols} cols`} />
                    )}
                    <MetaRow label="Docling Ref" value={
                      <span className="font-mono text-[10px] text-slate-500">{selected.docling_item_ref ?? '—'}</span>
                    } />
                  </div>
                </div>
              )}

              {activeTab === 'csv' && (
                <div>
                  {selected.has_csv ? (
                    <CsvTable projectId={pid} paperId={paperIdNum} assetId={selected.id} />
                  ) : (
                    <div className="flex flex-col items-center justify-center py-16 text-slate-300 gap-3">
                      <FileSpreadsheet size={40} strokeWidth={1} />
                      <div className="text-center">
                        <p className="text-sm font-medium text-slate-400">No CSV data</p>
                        <p className="text-xs text-slate-300 mt-1">
                          {selected.conversion_status === 'not_a_chart' && 'This figure was classified as not a chart.'}
                          {selected.conversion_status === 'skipped' && 'Chart conversion was skipped (PaddleOCR not installed).'}
                          {selected.conversion_status === 'failed' && (selected.conversion_error ?? 'Conversion failed.')}
                          {selected.asset_type === 'native_table' && 'Use the figure tab to view this table.'}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'caption' && (
                <div>
                  {selected.caption ? (
                    <div className="bg-slate-50 border border-slate-200 rounded-xl p-5">
                      <p className="text-sm text-slate-700 leading-relaxed italic">"{selected.caption}"</p>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-16 text-slate-300 gap-3">
                      <FileText size={36} strokeWidth={1} />
                      <p className="text-sm text-slate-400">No caption detected for this figure.</p>
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'context' && (
                <div className="space-y-3">
                  {!detail ? (
                    <div className="flex items-center gap-2 text-slate-400 text-sm py-8 justify-center">
                      <Loader2 size={14} className="animate-spin" /> Loading context…
                    </div>
                  ) : detail.context_links.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-16 text-slate-300 gap-3">
                      <Info size={36} strokeWidth={1} />
                      <p className="text-sm text-slate-400">No nearby text found.</p>
                    </div>
                  ) : (
                    detail.context_links.map((link, i) => {
                      const meta = LINK_LABELS[link.link_type] ?? { label: link.link_type, color: 'bg-slate-100 text-slate-500' }
                      const expanded = !!expandedLinks[i]
                      const isLong = link.text.length > 300
                      return (
                        <div key={i} className="border border-slate-100 rounded-xl overflow-hidden">
                          <div className="flex items-center gap-2 px-3 py-2 bg-slate-50 border-b border-slate-100">
                            <span className={clsx('text-[10px] font-semibold px-2 py-0.5 rounded-full', meta.color)}>{meta.label}</span>
                            {link.page_number && <span className="text-[10px] text-slate-400">p.{link.page_number}</span>}
                            <span className="ml-auto text-[10px] text-slate-300">score {link.score.toFixed(2)}</span>
                          </div>
                          <div className="px-3 py-2.5">
                            <p className="text-xs text-slate-600 leading-relaxed whitespace-pre-line">
                              {!expanded && isLong ? link.text.slice(0, 300) + '…' : link.text}
                            </p>
                            {isLong && (
                              <button
                                onClick={() => setExpandedLinks((p) => ({ ...p, [i]: !p[i] }))}
                                className="mt-1.5 flex items-center gap-1 text-[10px] text-blue-500 hover:text-blue-700"
                              >
                                {expanded ? <><ChevronUp size={10} />Show less</> : <><ChevronDown size={10} />Show more</>}
                              </button>
                            )}
                          </div>
                        </div>
                      )
                    })
                  )}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-slate-300">
            <div className="text-center">
              <BarChart3 size={48} strokeWidth={1} className="mx-auto mb-3" />
              <p className="text-sm text-slate-400">Select a figure from the list</p>
            </div>
          </div>
        )}
      </div>

      {/* ── Right: Extracted data + Validation ────────────────────── */}
      <div className="w-80 shrink-0 flex flex-col h-full">

        {/* Extracted Data */}
        <div className="flex-1 border-b border-slate-200 flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-200 shrink-0 flex items-center justify-between bg-slate-50">
            <div className="flex items-center gap-2">
              <FileSpreadsheet size={14} className="text-slate-500" />
              <h3 className="text-sm font-bold text-slate-700">Extracted Data</h3>
            </div>
            {selected?.has_csv && (
              <a
                href={workspaceApi.csvUrl(pid, paperIdNum, selected.id)}
                download={`figure_${selected.id}.csv`}
                className="flex items-center gap-1 text-[11px] text-blue-600 hover:text-blue-800 font-medium"
              >
                <Download size={11} />
                Download CSV
              </a>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-4">
            {selected?.has_csv ? (
              <CsvTable projectId={pid} paperId={paperIdNum} assetId={selected.id} />
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-slate-300 gap-2 py-8">
                <FileSpreadsheet size={32} strokeWidth={1} />
                <p className="text-xs text-slate-400 text-center">
                  {selected ? 'No CSV for this asset' : 'Select a figure'}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Validation & Messages */}
        <div className="shrink-0 flex flex-col max-h-72">
          <div className="px-4 py-3 border-b border-slate-200 shrink-0 bg-slate-50">
            <div className="flex items-center gap-2">
              <ShieldCheck size={14} className="text-slate-500" />
              <h3 className="text-sm font-bold text-slate-700">Validation & Messages</h3>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {selected ? (
              <ValidationChecks asset={selected} detail={detail} />
            ) : (
              <p className="text-xs text-slate-400 text-center py-4">Select a figure to validate</p>
            )}
          </div>
        </div>
      </div>

      </div>{/* end flex flex-1 overflow-hidden */}
    </div>
  )
}

