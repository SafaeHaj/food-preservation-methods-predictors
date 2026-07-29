/**
 * Scientific Database — the five-table schema the LLM pipeline produces.
 *
 * Experiments (meat matrix × treatment) with their ingredient links and their day/indicator
 * measurement grid, plus the reusable ingredient and indicator catalogues, and the
 * row-level evidence tying every value back to the PDF it came from.
 *
 * One field here is editable: an indicator's threshold. Papers rarely state the regulatory
 * limit their measurements are judged against, and shelf life is defined as the day that
 * limit is crossed — so without it nothing downstream can label an experiment. It used to
 * live on a separate "threshold definitions" screen, detached from the indicators it
 * applied to and matched back to them by string comparison on the measurement type.
 */

import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  AlertCircle, Beaker, ChevronDown, ChevronRight, FileText, FlaskConical, Gauge, Image as ImageIcon,
  Layers, Loader2, Quote, Table2,
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

import { usePapers } from '../../api/papers'
import {
  useExperiment, useExperiments, useIndicators, useIngredients, useUpdateIndicator,
} from '../../api/science'
import { errorMessage } from '../../api/errors'
import type {
  Evidence, ExperimentSummary, Indicator, Measurement,
} from '../../types/science'

type Tab = 'experiments' | 'ingredients' | 'indicators'

const FUNCTIONAL_CLASS_STYLES: Record<string, string> = {
  antimicrobial: 'bg-rose-50 text-rose-700 border-rose-100',
  antioxidant: 'bg-amber-50 text-amber-700 border-amber-100',
}

function classStyle(functionalClass: string): string {
  return FUNCTIONAL_CLASS_STYLES[functionalClass.toLowerCase()]
    ?? 'bg-slate-100 text-slate-600 border-slate-200'
}

function fmt(value: number): string {
  // Trim trailing zeros without lying about precision.
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)))
}

// ─── Measurement matrix (days × indicators) ─────────────────────────────────────

function MeasurementMatrix({ measurements }: { measurements: Measurement[] }) {
  const { days, indicators, cells } = useMemo(() => {
    const indicatorMap = new Map<number, Measurement>()
    const daySet = new Set<number>()
    const cellMap = new Map<string, Measurement>()
    for (const m of measurements) {
      if (!indicatorMap.has(m.indicator_id)) indicatorMap.set(m.indicator_id, m)
      daySet.add(m.day)
      cellMap.set(`${m.day}:${m.indicator_id}`, m)
    }
    return {
      days: [...daySet].sort((a, b) => a - b),
      indicators: [...indicatorMap.values()],
      cells: cellMap,
    }
  }, [measurements])

  if (measurements.length === 0) {
    return <p className="text-xs text-slate-400 italic">No measurements were extracted.</p>
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="text-xs w-full" style={{ fontVariantNumeric: 'tabular-nums' }}>
        <thead>
          <tr className="bg-slate-50 border-b border-slate-200">
            <th className="px-3 py-2 text-left font-semibold text-slate-600 whitespace-nowrap sticky left-0 bg-slate-50">
              Day
            </th>
            {indicators.map((ind) => (
              <th key={ind.indicator_id} className="px-3 py-2 text-left font-semibold text-slate-600 whitespace-nowrap">
                <div>{ind.indicator_type}</div>
                <div className="text-[10px] font-normal text-slate-400">
                  {ind.indicator_unit}
                  {ind.indicator_threshold != null && <> · limit {fmt(ind.indicator_threshold)}</>}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {days.map((day) => (
            <tr key={day} className="border-b border-slate-100 last:border-0 even:bg-slate-50/40">
              <td className="px-3 py-1.5 font-medium text-slate-700 sticky left-0 bg-white even:bg-slate-50/40">
                {day}
              </td>
              {indicators.map((ind) => {
                const cell = cells.get(`${day}:${ind.indicator_id}`)
                return (
                  <td key={ind.indicator_id} className="px-3 py-1.5 text-slate-700 whitespace-nowrap">
                    {cell ? (
                      <span title={cell.value_is_approximate ? 'Approximate (read from a chart)' : undefined}>
                        {cell.value_is_approximate && <span className="text-slate-400">≈ </span>}
                        {fmt(cell.indicator_value)}
                      </span>
                    ) : (
                      <span className="text-slate-300">—</span>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ─── Evidence ────────────────────────────────────────────────────────────────

const SOURCE_STYLES: Record<string, string> = {
  table: 'bg-blue-50 text-blue-700',
  chart: 'bg-violet-50 text-violet-700',
  figure: 'bg-violet-50 text-violet-700',
  text: 'bg-slate-100 text-slate-600',
  caption: 'bg-emerald-50 text-emerald-700',
}

function EvidenceItem({ item }: { item: Evidence }) {
  return (
    <div className="flex gap-3 border border-slate-100 rounded-lg p-2.5">
      {item.thumbnail_url && (
        <img
          src={item.thumbnail_url}
          alt=""
          className="w-16 h-16 object-cover rounded-md border border-slate-200 bg-slate-50 shrink-0"
          onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
        />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={clsx(
            'text-[10px] font-semibold px-2 py-0.5 rounded-full',
            SOURCE_STYLES[item.source_type] ?? 'bg-slate-100 text-slate-600',
          )}>
            {item.source_label ?? item.source_type}
          </span>
          {item.page_number != null && (
            <span className="text-[10px] text-slate-400">p.{item.page_number}</span>
          )}
          {item.is_chart_derived && (
            <span className="text-[10px] text-violet-500">chart-derived</span>
          )}
          {item.confidence != null && (
            <span className="ml-auto text-[10px] text-slate-300">{(item.confidence * 100).toFixed(0)}%</span>
          )}
        </div>
        {item.exact_text && (
          <p className="text-[11px] text-slate-600 leading-relaxed mt-1 line-clamp-3">
            <Quote size={9} className="inline text-slate-300 mr-0.5" />
            {item.exact_text}
          </p>
        )}
      </div>
    </div>
  )
}

// ─── One expandable experiment ─────────────────────────────────────────────────

function ExperimentRow({
  projectId, experiment,
}: { projectId: number; experiment: ExperimentSummary }) {
  const [open, setOpen] = useState(false)
  const { data: detail, isLoading } = useExperiment(projectId, open ? experiment.id : null)

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-50 transition-colors"
      >
        {open ? <ChevronDown size={15} className="text-slate-400 shrink-0" />
              : <ChevronRight size={15} className="text-slate-400 shrink-0" />}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-slate-900">{experiment.meat_matrix}</span>
            <span className="text-[11px] font-medium text-blue-700 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-100">
              {experiment.treatment}
            </span>
          </div>
          {experiment.ingredients.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap mt-1.5">
              {experiment.ingredients.map((ing) => (
                <span
                  key={ing.ingredient_id}
                  className={clsx('text-[10px] px-1.5 py-0.5 rounded border', classStyle(ing.functional_class))}
                  title={`${ing.functional_class} · ${ing.source}`}
                >
                  {ing.ingredient_name} · {fmt(ing.concentration)} {ing.concentration_unit}
                </span>
              ))}
            </div>
          )}
        </div>
        <span className="text-[11px] text-slate-400 shrink-0">
          {experiment.measurement_count} value{experiment.measurement_count !== 1 ? 's' : ''}
        </span>
        <span className="text-[10px] text-slate-300 font-mono shrink-0">#{experiment.id}</span>
      </button>

      {open && (
        <div className="border-t border-slate-100 px-4 py-4 bg-slate-50/40 space-y-4">
          {isLoading || !detail ? (
            <div className="flex items-center gap-2 text-xs text-slate-400 py-3">
              <Loader2 size={13} className="animate-spin" /> Loading measurements…
            </div>
          ) : (
            <>
              <section>
                <h4 className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-2 flex items-center gap-1.5">
                  <Table2 size={11} /> Measurements
                </h4>
                <MeasurementMatrix measurements={detail.measurements} />
              </section>

              {detail.evidence.length > 0 && (
                <section>
                  <h4 className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-2 flex items-center gap-1.5">
                    <ImageIcon size={11} /> Evidence ({detail.evidence.length})
                  </h4>
                  <div className="grid sm:grid-cols-2 gap-2">
                    {detail.evidence.map((item) => <EvidenceItem key={item.id} item={item} />)}
                  </div>
                </section>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Editable threshold ────────────────────────────────────────────────────────

/**
 * One indicator's threshold, edited in place.
 *
 * The draft is local until blur or Enter, so a partially-typed "1" on the way to "10" is
 * never sent — and never briefly makes the indicator look labelable at the wrong limit.
 * Escape restores the saved value. An empty field clears the threshold rather than saving
 * zero, which is a meaningful limit for several indicators.
 */
function ThresholdCell({
  projectId, indicator,
}: { projectId: number; indicator: Indicator }) {
  const saved = indicator.indicator_threshold
  const [draft, setDraft] = useState<string>(saved != null ? String(saved) : '')
  const [editing, setEditing] = useState(false)
  const update = useUpdateIndicator(projectId)

  // Follow the server when this row changes underneath us (another tab, a re-extraction),
  // but never while the field is focused — that would overwrite what is being typed.
  useEffect(() => {
    if (!editing) setDraft(saved != null ? String(saved) : '')
  }, [saved, editing])

  const commit = () => {
    setEditing(false)
    const trimmed = draft.trim()
    const next = trimmed === '' ? null : Number(trimmed)
    if (next !== null && !Number.isFinite(next)) {
      setDraft(saved != null ? String(saved) : '')
      return
    }
    if (next === saved) return

    update
      .mutateAsync({ indicatorId: indicator.id, indicator_threshold: next })
      .catch((error) => {
        toast.error(errorMessage(error, 'Could not save the threshold'))
        setDraft(saved != null ? String(saved) : '')
      })
  }

  return (
    <div className="flex items-center gap-1.5">
      <input
        type="number"
        step="any"
        value={draft}
        placeholder="—"
        onFocus={() => setEditing(true)}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.currentTarget.blur()
          if (e.key === 'Escape') {
            setDraft(saved != null ? String(saved) : '')
            setEditing(false)
            e.currentTarget.blur()
          }
        }}
        className={clsx(
          'w-24 px-2 py-1 text-sm rounded-md border transition-colors',
          'focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-400',
          saved != null
            ? 'border-slate-200 text-slate-800'
            : 'border-dashed border-slate-200 text-slate-400',
        )}
      />
      <span className="text-[10px] text-slate-400">{indicator.indicator_unit}</span>
    </div>
  )
}

// ─── Page ──────────────────────────────────────────────────────────────────────

function TabButton({ active, onClick, icon, label, count }: {
  active: boolean; onClick: () => void; icon: React.ReactNode; label: string; count?: number
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
        active ? 'bg-blue-600 text-white' : 'text-slate-500 hover:bg-slate-100',
      )}
    >
      {icon}{label}
      {count != null && (
        <span className={clsx('text-[10px]', active ? 'opacity-70' : 'text-slate-400')}>{count}</span>
      )}
    </button>
  )
}

export default function ScientificDatabasePage() {
  const { projectId } = useParams<{ projectId: string }>()
  const pid = Number(projectId)

  const [tab, setTab] = useState<Tab>('experiments')
  const [paperFilter, setPaperFilter] = useState<number | 'all'>('all')

  const { data: papers = [] } = usePapers(pid)
  const {
    data: experiments = [], isLoading: expLoading, error: expError,
  } = useExperiments(pid, paperFilter === 'all' ? undefined : paperFilter)
  const { data: ingredients = [] } = useIngredients(pid)
  const { data: indicators = [] } = useIndicators(pid)

  const paperName = useMemo(() => {
    const map = new Map(papers.map((p) => [p.id, p.original_name]))
    return (id: number) => map.get(id) ?? `Paper ${id}`
  }, [papers])

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-5">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Scientific Database</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Every experiment, ingredient, indicator and measurement extracted across this project.
          </p>
        </div>
        {papers.length > 0 && (
          <select
            value={paperFilter}
            onChange={(e) => setPaperFilter(e.target.value === 'all' ? 'all' : Number(e.target.value))}
            className="text-xs border border-slate-200 rounded-lg px-3 py-1.5 bg-white text-slate-700 max-w-xs"
          >
            <option value="all">All papers</option>
            {papers.map((p) => (
              <option key={p.id} value={p.id}>{p.original_name}</option>
            ))}
          </select>
        )}
      </div>

      <div className="flex items-center gap-1 border-b border-slate-100 pb-2">
        <TabButton active={tab === 'experiments'} onClick={() => setTab('experiments')}
          icon={<FlaskConical size={12} />} label="Experiments" count={experiments.length} />
        <TabButton active={tab === 'ingredients'} onClick={() => setTab('ingredients')}
          icon={<Beaker size={12} />} label="Ingredients" count={ingredients.length} />
        <TabButton active={tab === 'indicators'} onClick={() => setTab('indicators')}
          icon={<Gauge size={12} />} label="Indicators" count={indicators.length} />
      </div>

      {/* ── Experiments ─────────────────────────────────────────────────────── */}
      {tab === 'experiments' && (
        expError ? (
          <div className="text-center py-12 text-red-500 text-sm">
            {errorMessage(expError, 'Could not load extracted experiments')}
          </div>
        ) : expLoading ? (
          <div className="flex items-center gap-2 text-slate-400 py-8 text-sm">
            <Loader2 size={14} className="animate-spin" /> Loading experiments…
          </div>
        ) : experiments.length === 0 ? (
          <div className="text-center py-16 text-slate-300">
            <Layers size={40} strokeWidth={1} className="mx-auto mb-3" />
            <p className="text-sm text-slate-400">
              No structured data yet. Run a paper through the workspace and send it to the LLM.
            </p>
          </div>
        ) : (
          <div className="space-y-2.5">
            {paperFilter === 'all' && (
              <p className="text-[11px] text-slate-400">
                {experiments.length} experiment{experiments.length !== 1 ? 's' : ''} across all papers
              </p>
            )}
            {experiments.map((exp) => (
              <div key={exp.id}>
                {paperFilter === 'all' && (
                  <p className="text-[10px] text-slate-400 mb-1 ml-1 flex items-center gap-1">
                    <FileText size={9} /> {paperName(exp.paper_id)}
                  </p>
                )}
                <ExperimentRow projectId={pid} experiment={exp} />
              </div>
            ))}
          </div>
        )
      )}

      {/* ── Ingredients catalogue ───────────────────────────────────────────── */}
      {tab === 'ingredients' && (
        ingredients.length === 0 ? (
          <div className="text-center py-16 text-slate-300">
            <Beaker size={40} strokeWidth={1} className="mx-auto mb-3" />
            <p className="text-sm text-slate-400">No ingredients extracted yet.</p>
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-slate-200 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-slate-600">Ingredient</th>
                  <th className="px-3 py-2 text-left font-medium text-slate-600">Functional class</th>
                  <th className="px-3 py-2 text-left font-medium text-slate-600">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {ingredients.map((ing) => (
                  <tr key={ing.id} className="hover:bg-slate-50">
                    <td className="px-3 py-2 font-medium text-slate-800">{ing.ingredient_name}</td>
                    <td className="px-3 py-2">
                      <span className={clsx('text-[11px] px-1.5 py-0.5 rounded border', classStyle(ing.functional_class))}>
                        {ing.functional_class}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-slate-600">{ing.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* ── Indicators catalogue ────────────────────────────────────────────── */}
      {tab === 'indicators' && (
        indicators.length === 0 ? (
          <div className="text-center py-16 text-slate-300">
            <Gauge size={40} strokeWidth={1} className="mx-auto mb-3" />
            <p className="text-sm text-slate-400">No indicators extracted yet.</p>
          </div>
        ) : (
          <div className="space-y-2">
            <p className="text-[11px] text-slate-400">
              A threshold is the limit an indicator crosses to end shelf life. Set one to make
              the indicator usable for modelling; leave it blank if the paper gives none.
            </p>
            <div className="bg-white rounded-xl border border-slate-200 overflow-x-auto">
              <table className="w-full text-sm" style={{ fontVariantNumeric: 'tabular-nums' }}>
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium text-slate-600">Indicator</th>
                    <th className="px-3 py-2 text-left font-medium text-slate-600">Unit</th>
                    <th className="px-3 py-2 text-left font-medium text-slate-600">
                      Threshold / limit
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {indicators.map((ind) => (
                    <tr key={ind.id} className="hover:bg-slate-50">
                      <td className="px-3 py-2 font-medium text-slate-800">{ind.indicator_type}</td>
                      <td className="px-3 py-2 text-slate-600">{ind.indicator_unit}</td>
                      <td className="px-3 py-2">
                        <ThresholdCell projectId={pid} indicator={ind} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      )}
    </div>
  )
}
