import { useState } from 'react'
import { FileSpreadsheet, Image, Table2, BarChart2, Camera, Layers, HelpCircle, CheckCircle, Clock, AlertCircle, Star } from 'lucide-react'
import clsx from 'clsx'
import type { ExtractionAsset } from '../types/workspace'

const TYPE_ICONS: Record<string, React.ReactNode> = {
  chart:               <BarChart2 size={11} />,
  native_table:        <Table2 size={11} />,
  photograph:          <Camera size={11} />,
  diagram:             <Image size={11} />,
  chemical_structure:  <Image size={11} />,
  multi_panel_figure:  <Layers size={11} />,
  unknown:             <HelpCircle size={11} />,
}

const TYPE_COLORS: Record<string, string> = {
  chart:              'bg-emerald-100 text-emerald-700',
  native_table:       'bg-blue-100 text-blue-700',
  photograph:         'bg-slate-100 text-slate-600',
  diagram:            'bg-violet-100 text-violet-700',
  chemical_structure: 'bg-amber-100 text-amber-700',
  multi_panel_figure: 'bg-indigo-100 text-indigo-700',
  unknown:            'bg-slate-100 text-slate-500',
}

const CONV_BADGE: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  pending:        { label: 'Pending',     color: 'text-slate-400', icon: <Clock size={11} /> },
  processing:     { label: 'Processing',  color: 'text-blue-500',  icon: <Clock size={11} className="animate-spin" /> },
  complete:       { label: 'CSV ready',   color: 'text-emerald-600', icon: <CheckCircle size={11} /> },
  failed:         { label: 'Failed',      color: 'text-red-500',   icon: <AlertCircle size={11} /> },
  skipped:        { label: 'Skipped',     color: 'text-slate-400', icon: null },
  not_a_chart:    { label: 'Not a chart', color: 'text-slate-400', icon: null },
  not_applicable: { label: '',            color: '',               icon: null },
}

interface Props {
  asset: ExtractionAsset
  onClick: (asset: ExtractionAsset) => void
  onToggleSelect: (asset: ExtractionAsset, val: boolean) => void
}

export default function AssetCard({ asset, onClick, onToggleSelect }: Props) {
  const [imgError, setImgError] = useState(false)
  const [selecting, setSelecting] = useState(false)

  // Signed by the server and carried in the payload. The card cannot build this URL: the
  // signature is what authenticates the request, since <img> cannot send a bearer token.
  const imgUrl = asset.links.image
  const typeLabel = asset.asset_type === 'native_table' ? 'Table' : 'Figure'
  const conv = CONV_BADGE[asset.conversion_status ?? 'skipped'] ?? CONV_BADGE.skipped
  const typeColor = TYPE_COLORS[asset.classification] ?? TYPE_COLORS.unknown
  const typeIcon = TYPE_ICONS[asset.classification] ?? TYPE_ICONS.unknown

  const handleSelect = async (e: React.MouseEvent) => {
    e.stopPropagation()
    setSelecting(true)
    try {
      await onToggleSelect(asset, !asset.selected_for_llm)
    } finally {
      setSelecting(false)
    }
  }

  const score = asset.relevance_score ?? 0

  return (
    <div
      onClick={() => onClick(asset)}
      className={clsx(
        'group relative bg-white border rounded-xl overflow-hidden cursor-pointer transition-all duration-200',
        'hover:shadow-md hover:-translate-y-0.5',
        asset.selected_for_llm
          ? 'border-blue-400 shadow-sm shadow-blue-100 ring-1 ring-blue-300'
          : 'border-slate-200 hover:border-slate-300',
      )}
    >
      {/* Thumbnail area */}
      <div className="relative h-44 bg-slate-50 flex items-center justify-center overflow-hidden">
        {imgUrl && !imgError ? (
          <img
            src={imgUrl}
            alt={asset.caption ?? `${typeLabel} p.${asset.page_number}`}
            className="w-full h-full object-contain"
            onError={() => setImgError(true)}
          />
        ) : asset.asset_type === 'native_table' ? (
          <div className="flex flex-col items-center gap-2 text-slate-300">
            <Table2 size={36} />
            <span className="text-xs font-medium">Native Table</span>
            {asset.csv_rows !== null && (
              <span className="text-[10px]">{asset.csv_rows} rows × {asset.csv_cols} cols</span>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-1 text-slate-300">
            <Image size={36} />
            <span className="text-xs">No preview</span>
          </div>
        )}

        {/* Select for LLM button */}
        <button
          onClick={handleSelect}
          disabled={selecting}
          className={clsx(
            'absolute top-2 right-2 w-7 h-7 rounded-full flex items-center justify-center transition-all',
            'border shadow-sm text-[10px] font-bold',
            asset.selected_for_llm
              ? 'bg-blue-600 border-blue-600 text-white'
              : 'bg-white border-slate-200 text-slate-400 opacity-0 group-hover:opacity-100',
          )}
          title={asset.selected_for_llm ? 'Remove from LLM package' : 'Add to LLM package'}
        >
          {asset.selected_for_llm ? <CheckCircle size={14} /> : <Star size={14} />}
        </button>

        {/* Type badge */}
        <div className={clsx('absolute bottom-2 left-2 flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-semibold', typeColor)}>
          {typeIcon}
          {asset.classification !== 'unknown' ? asset.classification.replace('_', ' ') : typeLabel.toLowerCase()}
        </div>

        {/* Relevance score */}
        {score > 0 && (
          <div className="absolute bottom-2 right-2 bg-white/90 border border-slate-200 text-slate-600 text-[10px] font-semibold px-1.5 py-0.5 rounded-md">
            {score.toFixed(1)}
          </div>
        )}
      </div>

      {/* Info */}
      <div className="p-3 space-y-1.5">
        <div className="flex items-start justify-between gap-1">
          <p className="text-xs font-semibold text-slate-800 leading-snug">
            {typeLabel} · p.{asset.page_number ?? '?'}
          </p>
          {asset.section_name && (
            <span className="shrink-0 text-[10px] text-slate-400 truncate max-w-[80px]">{asset.section_name}</span>
          )}
        </div>

        {asset.caption ? (
          <p className="text-[11px] text-slate-500 leading-relaxed line-clamp-2">{asset.caption}</p>
        ) : (
          <p className="text-[11px] text-slate-300 italic">No caption</p>
        )}

        {/* Chart conversion status */}
        {asset.asset_type === 'figure' && conv.label && (
          <div className={clsx('flex items-center gap-1 text-[10px] font-medium', conv.color)}>
            {conv.icon}
            <span>{conv.label}</span>
            {asset.csv_rows !== null && asset.conversion_status === 'complete' && (
              <span className="text-slate-400 font-normal ml-1">
                {asset.csv_rows}r × {asset.csv_cols}c
              </span>
            )}
          </div>
        )}

        {/* Native table dimensions */}
        {asset.asset_type === 'native_table' && asset.csv_rows !== null && (
          <div className="flex items-center gap-1 text-[10px] text-emerald-600 font-medium">
            <FileSpreadsheet size={10} />
            {asset.csv_rows} rows × {asset.csv_cols} cols
          </div>
        )}
      </div>
    </div>
  )
}
