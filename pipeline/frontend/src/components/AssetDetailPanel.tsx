import { useEffect, useState } from 'react'
import { X, ExternalLink, FileSpreadsheet, CheckCircle, Star, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react'
import clsx from 'clsx'
import { workspaceApi } from '../services/api'
import type { ExtractionAsset, AssetDetail, ContextLink } from '../types/workspace'

const LINK_TYPE_LABELS: Record<string, { label: string; color: string }> = {
  caption:                   { label: 'Caption',           color: 'bg-blue-50 text-blue-700' },
  neighbor_before:           { label: 'Before',            color: 'bg-slate-100 text-slate-600' },
  neighbor_after:            { label: 'After',             color: 'bg-slate-100 text-slate-600' },
  explicit_figure_reference: { label: 'Explicit ref',      color: 'bg-emerald-50 text-emerald-700' },
  same_section:              { label: 'Same section',      color: 'bg-amber-50 text-amber-700' },
  keyword_match:             { label: 'Keyword match',     color: 'bg-violet-50 text-violet-600' },
}

interface CsvPreviewProps { projectId: number; paperId: number; assetId: number }

function CsvPreview({ projectId, paperId, assetId }: CsvPreviewProps) {
  const [rows, setRows] = useState<string[][]>([])
  const [error, setError] = useState(false)

  useEffect(() => {
    fetch(workspaceApi.csvUrl(projectId, paperId, assetId))
      .then((r) => r.text())
      .then((txt) => {
        const lines = txt.trim().split('\n').slice(0, 12)
        setRows(lines.map((l) => l.split(',').map((c) => c.trim().replace(/^"|"$/g, ''))))
      })
      .catch(() => setError(true))
  }, [projectId, paperId, assetId])

  if (error) return <p className="text-xs text-slate-400 italic">Could not load CSV preview.</p>
  if (!rows.length) return <p className="text-xs text-slate-400">Loading…</p>

  const [header, ...data] = rows
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="text-[11px] w-full">
        <thead>
          <tr className="bg-slate-50 border-b border-slate-200">
            {header.map((h, i) => (
              <th key={i} className="px-2.5 py-1.5 text-left font-semibold text-slate-600 whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, ri) => (
            <tr key={ri} className="border-b border-slate-100 last:border-0 even:bg-slate-50/50">
              {row.map((cell, ci) => (
                <td key={ci} className="px-2.5 py-1 text-slate-700 whitespace-nowrap">{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

interface ContextBlock { link: ContextLink; expanded: boolean; toggle: () => void }

function ContextItem({ link, expanded, toggle }: ContextBlock) {
  const meta = LINK_TYPE_LABELS[link.link_type] ?? { label: link.link_type, color: 'bg-slate-100 text-slate-600' }
  const short = link.text.length > 240 && !expanded
  return (
    <div className="border border-slate-100 rounded-lg overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2 bg-slate-50/80 border-b border-slate-100">
        <span className={clsx('text-[10px] font-semibold px-2 py-0.5 rounded-full', meta.color)}>{meta.label}</span>
        {link.page_number && (
          <span className="text-[10px] text-slate-400">p.{link.page_number}</span>
        )}
        <span className="ml-auto text-[10px] text-slate-300">{link.score.toFixed(2)}</span>
      </div>
      <div className="px-3 py-2">
        <p className="text-[12px] text-slate-600 leading-relaxed whitespace-pre-line">
          {short ? link.text.slice(0, 240) + '…' : link.text}
        </p>
        {link.text.length > 240 && (
          <button
            onClick={toggle}
            className="mt-1.5 flex items-center gap-1 text-[10px] text-blue-500 hover:text-blue-700"
          >
            {expanded ? <><ChevronUp size={11} />Show less</> : <><ChevronDown size={11} />Show more</>}
          </button>
        )}
      </div>
    </div>
  )
}

interface Props {
  asset: ExtractionAsset
  projectId: number
  paperId: number
  onClose: () => void
  onToggleSelect: (asset: ExtractionAsset, val: boolean) => void
}

export default function AssetDetailPanel({ asset, projectId, paperId, onClose, onToggleSelect }: Props) {
  const [detail, setDetail] = useState<AssetDetail | null>(null)
  const [imgTab, setImgTab] = useState<'figure' | 'page'>('figure')
  const [expanded, setExpanded] = useState<Record<number, boolean>>({})
  const [selecting, setSelecting] = useState(false)
  const [imgError, setImgError] = useState(false)

  useEffect(() => {
    workspaceApi.getAsset(projectId, paperId, asset.id).then(setDetail)
  }, [asset.id, projectId, paperId])

  const handleSelect = async () => {
    setSelecting(true)
    try {
      await onToggleSelect(asset, !asset.selected_for_llm)
    } finally {
      setSelecting(false)
    }
  }

  const toggleExpand = (i: number) =>
    setExpanded((prev) => ({ ...prev, [i]: !prev[i] }))

  const imgUrl = imgTab === 'figure'
    ? workspaceApi.imageUrl(projectId, paperId, asset.id)
    : workspaceApi.pageImageUrl(projectId, paperId, asset.id)

  const typeLabel = asset.asset_type === 'native_table' ? 'Table' : 'Figure'

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div className="flex-1 bg-black/30" onClick={onClose} />

      {/* Panel */}
      <div className="w-full max-w-3xl bg-white h-full shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-200 shrink-0">
          <div className="flex items-center gap-3">
            <h2 className="font-semibold text-slate-900 text-sm">
              {typeLabel} · Page {asset.page_number ?? '?'}
            </h2>
            {asset.section_name && (
              <span className="text-xs text-slate-400">{asset.section_name}</span>
            )}
            {asset.relevance_score > 0 && (
              <span className="text-xs font-semibold text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full">
                Score {asset.relevance_score.toFixed(1)}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleSelect}
              disabled={selecting}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors',
                asset.selected_for_llm
                  ? 'bg-blue-600 text-white hover:bg-blue-700'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
              )}
            >
              {asset.selected_for_llm ? <CheckCircle size={13} /> : <Star size={13} />}
              {asset.selected_for_llm ? 'In LLM package' : 'Add to LLM'}
            </button>
            <button onClick={onClose} className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors">
              <X size={18} className="text-slate-500" />
            </button>
          </div>
        </div>

        {/* Body — two columns */}
        <div className="flex-1 overflow-y-auto">
          <div className="grid grid-cols-2 divide-x divide-slate-200 min-h-full">

            {/* Left: image + CSV */}
            <div className="flex flex-col gap-4 p-4 overflow-y-auto">
              {/* Image tabs */}
              {(asset.has_image || asset.has_page_image) && (
                <>
                  <div className="flex gap-1 mb-1">
                    {asset.has_image && (
                      <button
                        onClick={() => setImgTab('figure')}
                        className={clsx(
                          'text-xs px-3 py-1 rounded-lg font-medium transition-colors',
                          imgTab === 'figure' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
                        )}
                      >
                        Figure
                      </button>
                    )}
                    {asset.has_page_image && (
                      <button
                        onClick={() => setImgTab('page')}
                        className={clsx(
                          'text-xs px-3 py-1 rounded-lg font-medium transition-colors',
                          imgTab === 'page' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
                        )}
                      >
                        Full page
                      </button>
                    )}
                    <a
                      href={imgUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="ml-auto flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 transition-colors"
                    >
                      <ExternalLink size={11} /> Open
                    </a>
                  </div>
                  {!imgError ? (
                    <img
                      key={imgUrl}
                      src={imgUrl}
                      alt={asset.caption ?? ''}
                      className="w-full rounded-lg border border-slate-200 object-contain bg-slate-50"
                      onError={() => setImgError(true)}
                    />
                  ) : (
                    <div className="h-40 bg-slate-50 rounded-lg border border-slate-200 flex items-center justify-center text-slate-400 text-xs">
                      Image unavailable
                    </div>
                  )}
                </>
              )}

              {/* CSV preview */}
              {asset.has_csv && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <FileSpreadsheet size={13} className="text-emerald-600" />
                    <span className="text-xs font-semibold text-slate-700">Chart CSV</span>
                    <span className="text-[10px] text-slate-400">
                      {asset.csv_rows}r × {asset.csv_cols}c
                    </span>
                    <a
                      href={workspaceApi.csvUrl(projectId, paperId, asset.id)}
                      download
                      className="ml-auto text-xs text-blue-500 hover:text-blue-700"
                    >
                      Download
                    </a>
                  </div>
                  <CsvPreview projectId={projectId} paperId={paperId} assetId={asset.id} />
                </div>
              )}

              {/* Native table CSV */}
              {asset.asset_type === 'native_table' && asset.has_csv && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <FileSpreadsheet size={13} className="text-blue-600" />
                    <span className="text-xs font-semibold text-slate-700">Table Data</span>
                    <a
                      href={workspaceApi.csvUrl(projectId, paperId, asset.id)}
                      download
                      className="ml-auto text-xs text-blue-500 hover:text-blue-700"
                    >
                      Download CSV
                    </a>
                  </div>
                  <CsvPreview projectId={projectId} paperId={paperId} assetId={asset.id} />
                </div>
              )}

              {/* Conversion warning */}
              {asset.conversion_status === 'failed' && asset.conversion_error && (
                <div className="flex gap-2 p-3 bg-red-50 border border-red-100 rounded-lg">
                  <AlertTriangle size={14} className="text-red-400 shrink-0 mt-0.5" />
                  <p className="text-xs text-red-600">{asset.conversion_error}</p>
                </div>
              )}
            </div>

            {/* Right: metadata + context */}
            <div className="flex flex-col gap-4 p-4 overflow-y-auto">
              {/* Asset info */}
              <div className="space-y-2">
                <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400">Details</h3>
                <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
                  <dt className="text-slate-400">Type</dt>
                  <dd className="text-slate-700 font-medium capitalize">{asset.classification.replace('_', ' ')}</dd>
                  <dt className="text-slate-400">Page</dt>
                  <dd className="text-slate-700 font-medium">{asset.page_number ?? '—'}</dd>
                  {asset.section_name && (
                    <>
                      <dt className="text-slate-400">Section</dt>
                      <dd className="text-slate-700 font-medium truncate">{asset.section_name}</dd>
                    </>
                  )}
                  <dt className="text-slate-400">Relevance</dt>
                  <dd className="text-amber-600 font-semibold">{(asset.relevance_score ?? 0).toFixed(1)} / 10</dd>
                  <dt className="text-slate-400">Ref</dt>
                  <dd className="text-slate-500 font-mono text-[10px]">{asset.docling_item_ref ?? '—'}</dd>
                </dl>
              </div>

              {/* Caption */}
              {asset.caption && (
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-1.5">Caption</h3>
                  <p className="text-[12px] text-slate-600 leading-relaxed italic">"{asset.caption}"</p>
                </div>
              )}

              {/* Context links */}
              {detail?.context_links && detail.context_links.length > 0 && (
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">
                    Related text ({detail.context_links.length})
                  </h3>
                  <div className="space-y-2">
                    {detail.context_links.map((link, i) => (
                      <ContextItem
                        key={i}
                        link={link}
                        expanded={!!expanded[i]}
                        toggle={() => toggleExpand(i)}
                      />
                    ))}
                  </div>
                </div>
              )}

              {detail && (!detail.context_links || detail.context_links.length === 0) && (
                <p className="text-xs text-slate-400 italic">No context links found.</p>
              )}
              {!detail && (
                <p className="text-xs text-slate-400">Loading context…</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
