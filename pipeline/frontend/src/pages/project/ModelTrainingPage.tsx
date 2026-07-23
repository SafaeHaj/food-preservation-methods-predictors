import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  BrainCircuit, TrendingUp, Zap, ChevronRight,
  X, BookOpen, Check, Info, Activity,
  BarChart3, Layers, Cpu, Loader2, AlertCircle,
  Play, RefreshCw, CheckCircle2, XCircle, Clock,
  FlaskConical, ChevronDown, History, Database,
} from 'lucide-react'
import clsx from 'clsx'
import { MODEL_DOCS, type ModelDoc } from '../../data/modelDocs'
import DatasetTab from '../../components/DatasetTab'
import {
  listDatasets, startTraining, listRuns, getRun, listModels, runPrediction,
  type BackendDataset, type TrainingRunStatus, type ModelResult, type PredictResult,
} from '../../services/modelLabApi'

// ─── Types ────────────────────────────────────────────────────────────────────
type Tab = 'dataset' | 'models' | 'train' | 'predict'

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'dataset', label: 'Dataset',        icon: <Cpu size={14} /> },
  { id: 'models',  label: 'Model Registry', icon: <Layers size={14} /> },
  { id: 'train',   label: 'Train',          icon: <Activity size={14} /> },
  { id: 'predict', label: 'Predict',        icon: <Zap size={14} /> },
]

// ─── Math doc helpers ─────────────────────────────────────────────────────────
function EquationBlock({ text }: { text: string }) {
  return (
    <pre className="text-[12px] leading-relaxed font-mono bg-slate-950 text-emerald-300 rounded-xl p-5 overflow-x-auto whitespace-pre">
      {text}
    </pre>
  )
}

function ParamsTable({ params }: { params: ModelDoc['params'] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="text-sm w-full">
        <thead>
          <tr className="bg-slate-50 border-b border-slate-200">
            <th className="text-left px-4 py-2.5 font-semibold text-slate-600 w-20">Symbol</th>
            <th className="text-left px-4 py-2.5 font-semibold text-slate-600">Parameter</th>
            <th className="text-left px-4 py-2.5 font-semibold text-slate-600 w-28">Unit</th>
            <th className="text-left px-4 py-2.5 font-semibold text-slate-600">Description</th>
          </tr>
        </thead>
        <tbody>
          {params.map((p, i) => (
            <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/60'}>
              <td className="px-4 py-2 font-mono text-violet-700 text-[12px]">{p.symbol}</td>
              <td className="px-4 py-2 font-medium text-slate-800">{p.name}</td>
              <td className="px-4 py-2 text-slate-500 text-[12px]">{p.unit}</td>
              <td className="px-4 py-2 text-slate-600">{p.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BulletList({ items, color = 'teal' }: { items: string[]; color?: string }) {
  const dot = color === 'violet' ? 'bg-violet-500' : 'bg-teal-500'
  return (
    <ul className="space-y-1.5">
      {items.map((item, i) => (
        <li key={i} className="flex items-start gap-2.5 text-sm text-slate-700">
          <span className={clsx('mt-1.5 w-1.5 h-1.5 rounded-full shrink-0', dot)} />
          {item}
        </li>
      ))}
    </ul>
  )
}

// ─── Model Guide Modal ────────────────────────────────────────────────────────
function ModelGuideModal({ model, onClose }: { model: ModelDoc; onClose: () => void }) {
  const isKinetic  = model.family === 'kinetic'
  const accentBg   = isKinetic ? 'from-teal-600 to-cyan-600' : 'from-violet-600 to-purple-600'
  const accentText = isKinetic ? 'text-teal-700' : 'text-violet-700'

  return (
    <div
      className="fixed inset-0 z-50 flex items-stretch justify-end bg-slate-900/50 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="w-full max-w-2xl bg-white shadow-2xl overflow-y-auto flex flex-col animate-in slide-in-from-right duration-300">
        <div className={clsx('bg-gradient-to-r text-white px-8 py-7 shrink-0', accentBg)}>
          <div className="flex items-start justify-between gap-4">
            <div>
              <span className="inline-block mb-2 text-[11px] font-bold uppercase tracking-widest bg-white/20 px-2.5 py-1 rounded-full">
                {isKinetic ? 'Kinetic Growth/Inactivation' : 'Survival Analysis'}
              </span>
              <h2 className="text-2xl font-bold leading-tight">{model.name}</h2>
              <p className="mt-1.5 text-white/80 text-sm">{model.tagline}</p>
            </div>
            <button onClick={onClose} className="mt-0.5 shrink-0 w-9 h-9 rounded-full bg-white/20 hover:bg-white/30 flex items-center justify-center transition-colors">
              <X size={16} />
            </button>
          </div>
        </div>
        <div className="flex-1 px-8 py-7 space-y-8">
          <section>
            <h3 className={clsx('text-sm font-bold uppercase tracking-wider mb-3', accentText)}>What this model does</h3>
            <p className="text-sm text-slate-700 leading-relaxed">{model.what}</p>
          </section>
          <section>
            <h3 className={clsx('text-sm font-bold uppercase tracking-wider mb-3', accentText)}>Best for</h3>
            <BulletList items={model.bestFor} color={model.family === 'survival' ? 'violet' : 'teal'} />
          </section>
          <section>
            <h3 className={clsx('text-sm font-bold uppercase tracking-wider mb-3', accentText)}>Mathematical Formulation</h3>
            <EquationBlock text={model.equation} />
            {model.equationNote && (
              <p className="mt-3 text-[12px] text-slate-500 leading-relaxed flex gap-2">
                <Info size={13} className="shrink-0 mt-0.5 text-slate-400" />
                {model.equationNote}
              </p>
            )}
          </section>
          <section>
            <h3 className={clsx('text-sm font-bold uppercase tracking-wider mb-3', accentText)}>Model Parameters</h3>
            <ParamsTable params={model.params} />
          </section>
          <section>
            <h3 className={clsx('text-sm font-bold uppercase tracking-wider mb-3', accentText)}>Data Requirements</h3>
            <BulletList items={model.dataRequirements} color={model.family === 'survival' ? 'violet' : 'teal'} />
          </section>
          <section>
            <h3 className={clsx('text-sm font-bold uppercase tracking-wider mb-3', accentText)}>Model Outputs</h3>
            <BulletList items={model.outputs} color={model.family === 'survival' ? 'violet' : 'teal'} />
          </section>
          <div className="grid grid-cols-2 gap-6">
            <section>
              <h3 className={clsx('text-sm font-bold uppercase tracking-wider mb-3', accentText)}>Assumptions</h3>
              <ul className="space-y-1.5">
                {model.assumptions.map((a, i) => (
                  <li key={i} className="flex items-start gap-2 text-[12px] text-slate-600">
                    <Check size={11} className="mt-1 shrink-0 text-green-500" />
                    {a}
                  </li>
                ))}
              </ul>
            </section>
            <section>
              <h3 className="text-sm font-bold uppercase tracking-wider mb-3 text-amber-600">Limitations</h3>
              <ul className="space-y-1.5">
                {model.limitations.map((l, i) => (
                  <li key={i} className="flex items-start gap-2 text-[12px] text-slate-600">
                    <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
                    {l}
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Model Card ───────────────────────────────────────────────────────────────
function ModelCard({
  model, result, runLabel, onGuide,
}: {
  model: ModelDoc
  result?: ModelResult
  runLabel?: string
  onGuide: (m: ModelDoc) => void
}) {
  const isKinetic = model.family === 'kinetic'
  const ring     = isKinetic ? 'ring-teal-200 hover:ring-teal-400' : 'ring-violet-200 hover:ring-violet-400'
  const badge    = isKinetic ? 'bg-teal-50 text-teal-700' : 'bg-violet-50 text-violet-700'
  const btnColor = isKinetic ? 'bg-teal-600 hover:bg-teal-700' : 'bg-violet-600 hover:bg-violet-700'

  const statusBadge = () => {
    if (!result) return (
      <span className="text-[11px] text-slate-400 border border-slate-200 rounded-full px-2.5 py-0.5 font-medium">Not trained</span>
    )
    if (result.status === 'completed') return (
      <span className="text-[11px] text-green-700 bg-green-50 border border-green-200 rounded-full px-2.5 py-0.5 font-medium flex items-center gap-1">
        <CheckCircle2 size={10} /> Trained
      </span>
    )
    if (result.status === 'skipped') return (
      <span className="text-[11px] text-amber-600 bg-amber-50 border border-amber-200 rounded-full px-2.5 py-0.5 font-medium">Skipped</span>
    )
    if (result.status === 'failed') return (
      <span className="text-[11px] text-red-600 bg-red-50 border border-red-200 rounded-full px-2.5 py-0.5 font-medium">Failed</span>
    )
    return (
      <span className="text-[11px] text-blue-600 bg-blue-50 border border-blue-200 rounded-full px-2.5 py-0.5 font-medium flex items-center gap-1">
        <Loader2 size={10} className="animate-spin" /> Training…
      </span>
    )
  }

  const metric = result?.status === 'completed'
    ? result.r_squared != null
      ? `R² = ${result.r_squared.toFixed(3)}`
      : result.concordance_index != null
        ? `C-index = ${result.concordance_index.toFixed(3)}`
        : null
    : result?.skip_reason ?? result?.error_message ?? null

  return (
    <div className={clsx(
      'group relative bg-white rounded-2xl ring-1 shadow-sm hover:shadow-md',
      'transition-all duration-200 overflow-hidden cursor-default flex flex-col', ring
    )}>
      <div className={clsx('h-1 w-full', isKinetic ? 'bg-gradient-to-r from-teal-400 to-cyan-400' : 'bg-gradient-to-r from-violet-500 to-purple-500')} />
      <div className="p-5 flex flex-col flex-1">
        <div className="flex items-start justify-between gap-2 mb-3">
          <span className={clsx('text-[11px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full', badge)}>
            {isKinetic ? 'Kinetic' : 'Survival'}
          </span>
          {statusBadge()}
        </div>
        <h3 className="font-bold text-slate-900 text-[15px] leading-snug">{model.name}</h3>
        <p className="mt-1.5 text-[12px] text-slate-500 leading-relaxed flex-1">{model.tagline}</p>
        {metric && (
          <p className={clsx(
            'mt-2 text-[12px] font-semibold',
            result?.status === 'completed' ? (isKinetic ? 'text-teal-700' : 'text-violet-700') : 'text-slate-400 italic'
          )}>
            {metric}
          </p>
        )}
        {runLabel && (
          <p className="mt-1 text-[11px] text-slate-400">{runLabel}</p>
        )}
        <div className="mt-4 flex items-center gap-2 pt-3 border-t border-slate-100">
          <button
            onClick={() => onGuide(model)}
            className={clsx(
              'flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-[12px] font-semibold text-white transition-colors shadow-sm',
              btnColor
            )}
          >
            <BookOpen size={12} /> View Guide
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Models Tab ───────────────────────────────────────────────────────────────
function ModelsTab({
  projectId, onGuide,
}: {
  projectId: number
  onGuide: (m: ModelDoc) => void
}) {
  const [registryModels, setRegistryModels] = useState<ModelResult[]>([])
  const [runs, setRuns]                     = useState<TrainingRunStatus[]>([])
  const [loading, setLoading]               = useState(true)

  useEffect(() => {
    Promise.all([listModels(projectId), listRuns(projectId)])
      .then(([models, r]) => { setRegistryModels(models); setRuns(r) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [projectId])

  const runMap = Object.fromEntries(runs.map((r) => [r.id, r]))

  // Group active completed/trained models by training_run_id
  const activeModels = registryModels.filter((m) => m.is_active && m.status === 'completed')
  const grouped: Record<number, ModelResult[]> = {}
  for (const m of activeModels) {
    if (!grouped[m.training_run_id]) grouped[m.training_run_id] = []
    grouped[m.training_run_id].push(m)
  }
  // Sort run groups by run id desc (newest first)
  const sortedRunIds = Object.keys(grouped).map(Number).sort((a, b) => b - a)

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 size={24} className="text-violet-500 animate-spin" />
      </div>
    )
  }

  if (sortedRunIds.length === 0) {
    return (
      <div className="space-y-8">
        {/* Show model cards as "not trained" when nothing is trained yet */}
        {['kinetic', 'survival'].map((family) => (
          <div key={family}>
            <div className="flex items-center gap-3 mb-5">
              <div className={clsx('w-9 h-9 rounded-xl flex items-center justify-center', family === 'kinetic' ? 'bg-teal-100' : 'bg-violet-100')}>
                {family === 'kinetic' ? <Activity size={16} className="text-teal-600" /> : <BarChart3 size={16} className="text-violet-600" />}
              </div>
              <div>
                <h2 className="font-bold text-slate-900 text-[15px]">
                  {family === 'kinetic' ? 'Kinetic Models' : 'Survival / AFT Models'}
                </h2>
                <p className="text-[12px] text-slate-500">
                  {family === 'kinetic' ? 'Model microbial growth or inactivation curves over time' : 'Predict time-to-failure from treatment covariates'}
                </p>
              </div>
            </div>
            <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
              {MODEL_DOCS.filter((m) => m.family === family).map((m) => (
                <ModelCard key={m.id} model={m} onGuide={onGuide} />
              ))}
            </div>
          </div>
        ))}
        <div className="flex items-start gap-3 bg-violet-50 border border-violet-100 rounded-xl px-5 py-4">
          <Info size={15} className="text-violet-500 shrink-0 mt-0.5" />
          <p className="text-[12px] text-violet-700 leading-relaxed">
            No models trained yet. Upload a dataset in the <strong>Dataset</strong> tab, then go to <strong>Train</strong>.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-10">
      {sortedRunIds.map((runId, idx) => {
        const run = runMap[runId]
        const runModels = grouped[runId]
        const kineticMods  = runModels.filter((m) => m.model_family === 'kinetic')
        const survivalMods = runModels.filter((m) => m.model_family === 'survival')
        const isLatest = idx === 0

        const docFor = (mr: ModelResult) =>
          MODEL_DOCS.find((d) => d.id === mr.model_name.toLowerCase())

        const runLabel = run
          ? `Run #${run.id} · ${run.dataset_name ?? `Dataset ${run.dataset_id}`} · ${new Date(run.created_at).toLocaleDateString()}`
          : `Run #${runId}`

        return (
          <div key={runId}>
            {/* Run header */}
            <div className="flex items-center gap-3 mb-5">
              <div className={clsx('w-9 h-9 rounded-xl flex items-center justify-center', isLatest ? 'bg-violet-600' : 'bg-slate-200')}>
                <History size={16} className={isLatest ? 'text-white' : 'text-slate-500'} />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h2 className="font-bold text-slate-900 text-[15px]">{runLabel}</h2>
                  {isLatest && (
                    <span className="text-[10px] font-bold uppercase tracking-wider bg-violet-100 text-violet-700 px-2 py-0.5 rounded-full">
                      Latest
                    </span>
                  )}
                </div>
                {run && (
                  <p className="text-[12px] text-slate-500">
                    {runModels.length} model{runModels.length !== 1 ? 's' : ''} trained
                    {run.n_trajectories > 0 && ` · ${run.n_trajectories} trajectories`}
                    {run.n_fitted > 0 && ` · ${run.n_fitted} fits`}
                  </p>
                )}
              </div>
            </div>

            {/* Kinetic models from this run */}
            {kineticMods.length > 0 && (
              <div className="mb-6">
                <p className="text-[11px] font-bold uppercase tracking-wider text-teal-600 mb-3 flex items-center gap-1.5">
                  <Activity size={12} /> Kinetic
                </p>
                <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
                  {kineticMods.map((mr) => {
                    const doc = docFor(mr)
                    return doc ? (
                      <ModelCard
                        key={mr.id}
                        model={doc}
                        result={mr}
                        runLabel={`Run #${runId}`}
                        onGuide={onGuide}
                      />
                    ) : (
                      <div key={mr.id} className="rounded-2xl border border-slate-200 bg-white p-4">
                        <p className="font-semibold text-slate-700">{mr.model_name}</p>
                        {mr.r_squared != null && (
                          <p className="text-[12px] text-teal-700 mt-1">R² = {mr.r_squared.toFixed(3)}</p>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Survival models from this run */}
            {survivalMods.length > 0 && (
              <div>
                <p className="text-[11px] font-bold uppercase tracking-wider text-violet-600 mb-3 flex items-center gap-1.5">
                  <BarChart3 size={12} /> Survival / AFT
                </p>
                <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
                  {survivalMods.map((mr) => {
                    const doc = docFor(mr)
                    return doc ? (
                      <ModelCard
                        key={mr.id}
                        model={doc}
                        result={mr}
                        runLabel={`Run #${runId}`}
                        onGuide={onGuide}
                      />
                    ) : (
                      <div key={mr.id} className="rounded-2xl border border-slate-200 bg-white p-4">
                        <p className="font-semibold text-slate-700">{mr.model_name}</p>
                        {mr.concordance_index != null && (
                          <p className="text-[12px] text-violet-700 mt-1">C = {mr.concordance_index.toFixed(3)}</p>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {idx < sortedRunIds.length - 1 && <div className="mt-8 border-t border-slate-100" />}
          </div>
        )
      })}

      <div className="flex items-start gap-3 bg-violet-50 border border-violet-100 rounded-xl px-5 py-4">
        <Info size={15} className="text-violet-500 shrink-0 mt-0.5" />
        <p className="text-[12px] text-violet-700 leading-relaxed">
          Click <strong>View Guide</strong> to see the full mathematical formulation and data requirements.
          Each training run is listed separately so you can compare results across runs.
        </p>
      </div>
    </div>
  )
}

// ─── Run Model Row ────────────────────────────────────────────────────────────
function RunModelRow({ result }: { result: ModelResult }) {
  const icons: Record<string, React.ReactNode> = {
    pending:  <Clock size={13} className="text-slate-400" />,
    training: <Loader2 size={13} className="text-blue-500 animate-spin" />,
    completed:<CheckCircle2 size={13} className="text-green-500" />,
    failed:   <XCircle size={13} className="text-red-400" />,
    skipped:  <Info size={13} className="text-amber-500" />,
  }
  const icon = icons[result.status] ?? icons.pending

  const metric = result.r_squared != null
    ? `R² ${result.r_squared.toFixed(3)}`
    : result.concordance_index != null
      ? `C ${result.concordance_index.toFixed(3)}`
      : result.mae != null
        ? `MAE ${result.mae.toFixed(3)}`
        : '—'

  const borderCls =
    result.status === 'completed' ? 'border-green-200 bg-green-50'
    : result.status === 'failed'  ? 'border-red-200 bg-red-50'
    : result.status === 'skipped' ? 'border-amber-200 bg-amber-50'
    : result.status === 'training'? 'border-blue-200 bg-blue-50/50'
    : 'border-slate-200 bg-white'

  const statusCls =
    result.status === 'completed' ? 'text-green-700 bg-green-100'
    : result.status === 'failed'  ? 'text-red-600 bg-red-100'
    : result.status === 'skipped' ? 'text-amber-700 bg-amber-100'
    : result.status === 'training'? 'text-blue-700 bg-blue-100'
    : 'text-slate-500 bg-slate-100'

  const displayName =
    MODEL_DOCS.find((d) => d.id === result.model_name)?.name ?? result.model_name

  return (
    <div className={clsx('flex items-center gap-3 px-4 py-3 rounded-lg border', borderCls)}>
      {icon}
      <span className="flex-1 text-[13px] font-semibold text-slate-800">{displayName}</span>
      {result.status === 'completed' && (
        <span className="text-[12px] font-mono text-slate-600">{metric}</span>
      )}
      {(result.status === 'failed' || result.status === 'skipped') && (
        <span className="text-[11px] text-slate-500 max-w-[200px] truncate">
          {result.error_message ?? result.skip_reason ?? ''}
        </span>
      )}
      <span className={clsx('text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full', statusCls)}>
        {result.status}
      </span>
    </div>
  )
}

// ─── Run History Item ─────────────────────────────────────────────────────────
function RunHistoryItem({ run }: { run: TrainingRunStatus }) {
  const [open, setOpen] = useState(false)

  const statusColor =
    run.status === 'completed' ? 'text-green-600 bg-green-50 border-green-200'
    : run.status === 'failed'  ? 'text-red-600 bg-red-50 border-red-100'
    : 'text-blue-600 bg-blue-50 border-blue-100'

  const family = run.dataset_family ?? 'kinetic'

  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-4 py-3 bg-white hover:bg-slate-50 transition-colors text-left"
      >
        <div className="w-7 h-7 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
          {run.status === 'completed'
            ? <CheckCircle2 size={13} className="text-green-500" />
            : run.status === 'failed'
            ? <XCircle size={13} className="text-red-400" />
            : <Loader2 size={13} className="text-blue-500 animate-spin" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[13px] font-semibold text-slate-800">Run #{run.id}</span>
            <span className={clsx('text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border', statusColor)}>
              {run.status}
            </span>
            <span className="text-[11px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
              {family}
            </span>
          </div>
          <div className="flex items-center gap-3 mt-0.5">
            <span className="text-[12px] text-slate-500 flex items-center gap-1">
              <Database size={10} />
              {run.dataset_name ?? `Dataset #${run.dataset_id}`}
            </span>
            <span className="text-[12px] text-slate-400">
              {new Date(run.created_at).toLocaleDateString()} {new Date(run.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
            {run.n_fitted > 0 && (
              <span className="text-[12px] text-slate-500">{run.n_fitted} fitted</span>
            )}
          </div>
        </div>
        <ChevronDown
          size={14}
          className={clsx('text-slate-400 shrink-0 transition-transform duration-200', open && 'rotate-180')}
        />
      </button>

      {open && run.model_results && run.model_results.length > 0 && (
        <div className="px-4 pb-4 pt-1 bg-slate-50/50 border-t border-slate-100 space-y-2">
          {run.model_results.map((r) => (
            <RunModelRow key={r.id} result={r} />
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Train Tab ────────────────────────────────────────────────────────────────
const TRAIN_STEPS: Record<string, number> = {
  queued: 0,
  'Queued': 0,
  'Loading dataset': 1,
  'Fitting kinetic models': 2,
  'Fitting survival models': 2,
  'Fitting models': 2,
  'Saving model results': 3,
  'Done': 4,
}

function TrainProgressBar({ run }: { run: TrainingRunStatus }) {
  const progress = run.job?.progress ?? 0
  const step = run.job?.current_step ?? (run.status === 'queued' ? 'Queued' : '')
  const stepIdx = TRAIN_STEPS[step] ?? 0

  const steps = ['Queue', 'Load data', 'Fit models', 'Save results']

  return (
    <div className="space-y-3">
      {/* Progress bar */}
      <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-violet-500 to-purple-500 rounded-full transition-all duration-700"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Step dots */}
      <div className="flex items-center justify-between px-1">
        {steps.map((s, i) => (
          <div key={s} className="flex flex-col items-center gap-1">
            <div className={clsx(
              'w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold transition-colors',
              i < stepIdx  ? 'bg-violet-500 text-white'
              : i === stepIdx ? 'bg-violet-200 text-violet-700 ring-2 ring-violet-400'
              : 'bg-slate-200 text-slate-400'
            )}>
              {i < stepIdx ? <Check size={10} /> : i + 1}
            </div>
            <span className={clsx('text-[10px] font-medium', i <= stepIdx ? 'text-violet-600' : 'text-slate-400')}>{s}</span>
          </div>
        ))}
      </div>

      {step && step !== 'Done' && (
        <p className="text-[12px] text-slate-500 text-center">{step}…</p>
      )}
    </div>
  )
}

function TrainTab({
  projectId,
  onGoToDataset,
}: {
  projectId: number
  onGoToDataset: () => void
}) {
  const [dataset, setDataset]   = useState<BackendDataset | null>(null)
  const [allRuns, setAllRuns]   = useState<TrainingRunStatus[]>([])
  const [threshold, setThreshold] = useState('7.0')
  const [loading, setLoading]   = useState(true)
  const [starting, setStarting] = useState(false)
  const [error, setError]       = useState<string | null>(null)
  const pollRef                 = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    Promise.all([
      listDatasets(projectId).then((ds) => ds.find((d) => d.parse_status === 'ready') ?? null),
      listRuns(projectId),
    ])
      .then(([ds, runs]) => { setDataset(ds); setAllRuns(runs) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [projectId])

  const latestRun = allRuns[0] ?? null
  const isRunning = latestRun && (latestRun.status === 'queued' || latestRun.status === 'running')

  useEffect(() => {
    if (isRunning && latestRun) {
      pollRef.current = setInterval(() => {
        getRun(projectId, latestRun.id).then((updated) => {
          setAllRuns((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
          if (updated.status === 'completed' || updated.status === 'failed') {
            clearInterval(pollRef.current!)
          }
        }).catch(() => {})
      }, 2500)
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [projectId, latestRun?.id, latestRun?.status])

  const handleStart = async () => {
    if (!dataset) return
    setStarting(true); setError(null)
    try {
      const mapping = dataset.column_mapping as Record<string, string>
      const family  = dataset.dataset_family ?? 'kinetic'
      const thr     = family === 'kinetic' ? parseFloat(threshold) : undefined
      const { training_run_id } = await startTraining(projectId, dataset.id, mapping, family, thr)
      const newRun = await getRun(projectId, training_run_id)
      setAllRuns((prev) => [newRun, ...prev])
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to start training')
    } finally {
      setStarting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 size={24} className="text-violet-500 animate-spin" />
      </div>
    )
  }

  if (!dataset || !Object.keys(dataset.column_mapping ?? {}).length) {
    return (
      <div className="flex flex-col items-center justify-center py-24 space-y-5">
        <div className="w-16 h-16 rounded-2xl bg-violet-100 flex items-center justify-center">
          <Cpu size={28} className="text-violet-500" />
        </div>
        <div className="text-center max-w-sm">
          <h2 className="text-lg font-bold text-slate-900 mb-1">No dataset ready</h2>
          <p className="text-sm text-slate-500 leading-relaxed">
            Upload and map a dataset first, then return here to train.
          </p>
        </div>
        <button
          onClick={onGoToDataset}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-700 text-white font-semibold text-sm transition-colors"
        >
          Go to Dataset <ChevronRight size={14} />
        </button>
      </div>
    )
  }

  const family = (dataset.dataset_family ?? 'kinetic') as 'kinetic' | 'survival'
  const historyRuns = allRuns.slice(1)

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h2 className="text-lg font-bold text-slate-900">Train Models</h2>
        <p className="text-sm text-slate-500 mt-0.5">
          All {family} models will be fitted on{' '}
          <strong>{dataset.original_name}</strong> ({dataset.row_count.toLocaleString()} rows).
        </p>
      </div>

      {/* Config — only when not training */}
      {!isRunning && (
        <div className="bg-white border border-slate-200 rounded-2xl p-6 space-y-4">
          {family === 'kinetic' && (
            <label className="block">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 block mb-1.5">
                Failure threshold (log CFU/g)
              </span>
              <input
                type="number"
                step="0.5"
                min="1"
                max="12"
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-violet-400 focus:border-transparent transition"
              />
              <p className="text-[11px] text-slate-400 mt-1">
                Count above this threshold = product failure (default 7 log CFU/g)
              </p>
            </label>
          )}

          {error && (
            <div className="flex gap-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
              <AlertCircle size={15} className="text-red-500 shrink-0 mt-0.5" />
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          <button
            disabled={starting}
            onClick={handleStart}
            className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-700 disabled:opacity-50 text-white font-semibold text-sm transition-colors shadow-sm shadow-violet-100"
          >
            {starting
              ? <><Loader2 size={14} className="animate-spin" /> Starting…</>
              : <><Play size={14} /> Start Training</>}
          </button>
        </div>
      )}

      {/* Current / latest run */}
      {latestRun && (
        <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
          {/* Run header */}
          <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100">
            <div className="flex items-center gap-2 min-w-0">
              {isRunning && <Loader2 size={14} className="text-violet-500 animate-spin shrink-0" />}
              {latestRun.status === 'completed' && <CheckCircle2 size={14} className="text-green-500 shrink-0" />}
              {latestRun.status === 'failed' && <XCircle size={14} className="text-red-400 shrink-0" />}
              <div className="min-w-0">
                <span className="text-sm font-semibold text-slate-800">
                  {isRunning ? 'Training in progress…' : `Training ${latestRun.status}`}
                </span>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[11px] text-slate-400">
                    Run #{latestRun.id} · {latestRun.dataset_name ?? `Dataset #${latestRun.dataset_id}`}
                  </span>
                </div>
              </div>
            </div>
            {!isRunning && (
              <button
                onClick={handleStart}
                disabled={starting}
                className="flex items-center gap-1.5 text-[12px] text-slate-500 hover:text-violet-600 transition-colors shrink-0"
              >
                <RefreshCw size={12} /> Re-train
              </button>
            )}
          </div>

          {/* Progress bar during training */}
          {isRunning && (
            <div className="px-5 pt-4 pb-2">
              <TrainProgressBar run={latestRun} />
            </div>
          )}

          {/* Model rows */}
          <div className="p-4 space-y-2">
            {latestRun.model_results && latestRun.model_results.length > 0
              ? latestRun.model_results.map((r) => <RunModelRow key={r.id} result={r} />)
              : (
                <div className="grid grid-cols-2 gap-2">
                  {MODEL_DOCS.filter((m) => m.family === family).map((m) => (
                    <div key={m.id} className="flex items-center gap-2 px-4 py-3 rounded-lg border border-slate-200 bg-white">
                      <Clock size={13} className="text-slate-300" />
                      <span className="text-[13px] text-slate-400">{m.name}</span>
                    </div>
                  ))}
                </div>
              )
            }
          </div>

          {latestRun.status === 'completed' && latestRun.n_fitted != null && (
            <div className="px-5 py-3 border-t border-slate-100 bg-green-50/50">
              <p className="text-[12px] text-green-700">
                <strong>{latestRun.n_fitted}</strong> model{latestRun.n_fitted !== 1 ? 's' : ''} fitted
                {latestRun.n_trajectories > 0 && ` across ${latestRun.n_trajectories} trajectories`}.
                Go to <strong>Model Registry</strong> to see metrics and <strong>Predict</strong> to run predictions.
              </p>
            </div>
          )}

          {latestRun.status === 'failed' && latestRun.error_message && (
            <div className="px-5 py-3 border-t border-red-100 bg-red-50">
              <p className="text-[12px] text-red-700">{latestRun.error_message}</p>
            </div>
          )}
        </div>
      )}

      {/* Training History */}
      {historyRuns.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <History size={14} className="text-slate-400" />
            <h3 className="text-sm font-semibold text-slate-600">Previous Runs</h3>
          </div>
          <div className="space-y-2">
            {historyRuns.map((r) => (
              <RunHistoryItem key={r.id} run={r} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Predict Tab ──────────────────────────────────────────────────────────────
const NUMERIC_COL_HINTS = ['temp', 'ph', 'aw', 'water', 'conc', 'dose', 'time', 'day', 'hour', 'count', 'ppm', 'mg']

function guessInputType(col: string): 'number' | 'text' {
  const lower = col.toLowerCase()
  return NUMERIC_COL_HINTS.some((h) => lower.includes(h)) ? 'number' : 'text'
}

function KineticModelSummary({ models, runs }: { models: ModelResult[]; runs: TrainingRunStatus[] }) {
  const runMap = Object.fromEntries(runs.map((r) => [r.id, r]))
  const [selectedId, setSelectedId] = useState<number>(models[0]?.id ?? 0)
  const selected = models.find((m) => m.id === selectedId) ?? models[0]

  const inputCls = 'w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent transition'

  if (!selected) return null
  const run = runMap[selected.training_run_id]
  const doc = MODEL_DOCS.find((d) => d.id === selected.model_name)

  return (
    <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
      <div className="lg:col-span-2 space-y-5">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Kinetic Model Summary</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            Select a kinetic model to review its fit quality across trajectories.
          </p>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <label className="block">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 block mb-1.5">Model</span>
            <select
              value={selectedId}
              onChange={(e) => setSelectedId(parseInt(e.target.value, 10))}
              className={inputCls}
            >
              {models.map((m) => {
                const r = runMap[m.training_run_id]
                const label = MODEL_DOCS.find((d) => d.id === m.model_name)?.name ?? m.model_name
                return (
                  <option key={m.id} value={m.id}>
                    {label} — Run #{m.training_run_id} ({r?.dataset_name ?? `ds#${m.training_run_id}`})
                  </option>
                )
              })}
            </select>
          </label>
        </div>

        <div className="bg-teal-50 border border-teal-100 rounded-xl px-5 py-4 flex items-start gap-3">
          <Info size={14} className="text-teal-500 shrink-0 mt-0.5" />
          <p className="text-[12px] text-teal-700 leading-relaxed">
            Kinetic models fit growth/inactivation curves <strong>per trajectory</strong>.
            They don't predict shelf life from covariate inputs — use the <strong>Model Registry</strong> for full trajectory details.
            To predict shelf life from formulation conditions, train a <strong>Survival</strong> dataset.
          </p>
        </div>
      </div>

      <div className="lg:col-span-3 space-y-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Fit Quality</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            {doc?.name ?? selected.model_name} · Run #{selected.training_run_id}
            {run && ` · ${run.dataset_name ?? `Dataset #${selected.training_run_id}`}`}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          {selected.r_squared != null && (
            <div className="rounded-2xl border border-teal-200 bg-teal-50 p-5">
              <p className="text-[11px] font-bold uppercase tracking-wider text-teal-500 mb-2">Mean R²</p>
              <p className="text-3xl font-black text-teal-800">{selected.r_squared.toFixed(3)}</p>
              <p className="text-[11px] text-teal-500 mt-1">Goodness of fit across all trajectories</p>
            </div>
          )}
          {selected.mae != null && (
            <div className="rounded-2xl border border-slate-200 bg-white p-5">
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">Mean MAE</p>
              <p className="text-3xl font-black text-slate-800">{selected.mae.toFixed(3)}</p>
              <p className="text-[11px] text-slate-400 mt-1">Mean absolute error (log CFU/g)</p>
            </div>
          )}
        </div>

        {selected.metrics && Object.keys(selected.metrics).length > 0 && (
          <div className="bg-white rounded-2xl border border-slate-200 p-5">
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-3">Detailed Metrics</p>
            <div className="space-y-2">
              {Object.entries(selected.metrics)
                .filter(([, v]) => v != null)
                .map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between text-sm">
                    <span className="text-slate-600 capitalize">{k.replace(/_/g, ' ')}</span>
                    <span className="font-mono text-slate-800">{typeof v === 'number' ? v.toFixed(4) : String(v)}</span>
                  </div>
                ))}
            </div>
          </div>
        )}

        <div className="bg-white rounded-2xl border border-slate-200 px-5 py-3">
          <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">Training Source</p>
          <p className="text-sm text-slate-700 font-medium">
            {doc?.name ?? selected.model_name} · Run #{selected.training_run_id}
          </p>
          {run && (
            <p className="text-[12px] text-slate-400 mt-0.5">
              {run.dataset_name ?? `Dataset #${run.dataset_id}`} ·{' '}
              {new Date(run.created_at).toLocaleDateString()}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

function SurvivalPredictPanel({
  projectId, models, runs,
}: {
  projectId: number
  models: ModelResult[]
  runs: TrainingRunStatus[]
}) {
  const runMap = Object.fromEntries(runs.map((r) => [r.id, r]))
  const [selectedId, setSelectedId]   = useState<number>(models[0]?.id ?? 0)
  const [featureValues, setFeatureValues] = useState<Record<string, string>>({})
  const [targetDays, setTargetDays]   = useState('')
  const [predicting, setPredicting]   = useState(false)
  const [result, setResult]           = useState<PredictResult | null>(null)
  const [predError, setPredError]     = useState<string | null>(null)

  useEffect(() => {
    setFeatureValues({})
    setResult(null)
    setPredError(null)
  }, [selectedId])

  const selectedModel = models.find((m) => m.id === selectedId)
  const featureCols   = selectedModel?.feature_cols ?? []
  const selectedRun   = selectedModel ? runMap[selectedModel.training_run_id] : undefined

  const handlePredict = async () => {
    if (!selectedId) return
    setPredicting(true); setPredError(null); setResult(null)
    try {
      const features: Record<string, unknown> = {}
      for (const [col, val] of Object.entries(featureValues)) {
        if (val === '') continue
        const numVal = parseFloat(val)
        features[col] = isNaN(numVal) ? val : numVal
      }
      const r = await runPrediction(
        projectId, selectedId, features,
        targetDays ? parseFloat(targetDays) : undefined,
      )
      setResult(r)
    } catch (e: unknown) {
      setPredError(e instanceof Error ? e.message : 'Prediction failed')
    } finally {
      setPredicting(false)
    }
  }

  const inputCls = 'w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-violet-400 focus:border-transparent transition'

  return (
    <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
      {/* Form */}
      <div className="lg:col-span-2 space-y-5">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Test a New Formulation</h2>
          <p className="text-sm text-slate-500 mt-0.5">Enter covariate values to predict shelf life.</p>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
          <label className="block">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 block mb-1.5">
              Survival Model
            </span>
            <select
              value={selectedId}
              onChange={(e) => setSelectedId(parseInt(e.target.value, 10))}
              className={inputCls}
            >
              {models.map((m) => {
                const run = runMap[m.training_run_id]
                const label = MODEL_DOCS.find((d) => d.id === m.model_name)?.name ?? m.model_name
                const dsName = run?.dataset_name ?? `ds#${m.training_run_id}`
                return (
                  <option key={m.id} value={m.id}>
                    {label} — Run #{m.training_run_id} ({dsName})
                  </option>
                )
              })}
            </select>
          </label>

          {selectedRun && (
            <p className="text-[11px] text-slate-400">
              Trained {new Date(selectedRun.created_at).toLocaleDateString()} · {selectedRun.dataset_name ?? `Dataset #${selectedRun.dataset_id}`}
              {selectedModel?.concordance_index != null && ` · C-index ${selectedModel.concordance_index.toFixed(3)}`}
            </p>
          )}
        </div>

        {featureCols.length > 0 && (
          <div className="bg-white border border-slate-200 rounded-2xl p-6 space-y-4">
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Covariate Values</p>
            <div className="grid grid-cols-2 gap-3">
              {featureCols.map((col) => (
                <label key={col} className="block">
                  <span className="text-[11px] font-semibold text-slate-600 mb-1 block">{col}</span>
                  <input
                    type={guessInputType(col)}
                    step="any"
                    placeholder={guessInputType(col) === 'number' ? '0' : 'value'}
                    value={featureValues[col] ?? ''}
                    onChange={(e) => setFeatureValues((p) => ({ ...p, [col]: e.target.value }))}
                    className={inputCls}
                  />
                </label>
              ))}
            </div>

            <div className="pt-2 border-t border-slate-100">
              <label className="block">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400 block mb-1.5">
                  Required shelf life (days) — optional
                </span>
                <input
                  type="number"
                  placeholder="e.g. 21"
                  value={targetDays}
                  onChange={(e) => setTargetDays(e.target.value)}
                  className={inputCls}
                />
                <p className="text-[11px] text-slate-400 mt-1">When set, computes P(shelf life ≥ target)</p>
              </label>
            </div>

            {predError && (
              <div className="flex gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                <AlertCircle size={13} className="text-red-500 shrink-0 mt-0.5" />
                <p className="text-[12px] text-red-700">{predError}</p>
              </div>
            )}

            <button
              onClick={handlePredict}
              disabled={predicting || !selectedId}
              className="w-full py-2.5 rounded-xl bg-violet-600 hover:bg-violet-700 disabled:opacity-50 text-white font-semibold text-sm transition-colors shadow-sm shadow-violet-200 flex items-center justify-center gap-2"
            >
              {predicting
                ? <><Loader2 size={14} className="animate-spin" /> Predicting…</>
                : <><Zap size={14} /> Predict Shelf Life</>}
            </button>
          </div>
        )}
      </div>

      {/* Output */}
      <div className="lg:col-span-3 space-y-6">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Prediction Output</h2>
          <p className="text-sm text-slate-500 mt-0.5">Results appear here after submitting a formulation.</p>
        </div>

        {!result && !predicting ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50/40 py-24 text-center">
            <TrendingUp size={36} className="text-slate-300 mb-4" />
            <p className="text-slate-400 text-sm font-medium">No prediction yet</p>
            <p className="text-slate-400 text-[12px] mt-1">Fill in the covariate values and click Predict</p>
          </div>
        ) : predicting ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-slate-200 bg-slate-50 py-24">
            <Loader2 size={28} className="text-violet-500 animate-spin mb-3" />
            <p className="text-sm text-slate-500">Running prediction…</p>
          </div>
        ) : result ? (
          <div className="space-y-4">
            {result.error && (
              <div className="flex gap-3 bg-red-50 border border-red-200 rounded-xl px-5 py-4">
                <AlertCircle size={15} className="text-red-500 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-red-800">Prediction error</p>
                  <p className="text-[12px] text-red-700 mt-0.5">{result.error}</p>
                </div>
              </div>
            )}

            {!result.error && (
              <div className="grid grid-cols-2 gap-4">
                <div className="rounded-2xl border border-violet-200 bg-violet-50 p-5">
                  <p className="text-[11px] font-bold uppercase tracking-wider text-violet-500 mb-2">Predicted shelf life</p>
                  <p className="text-3xl font-black text-violet-800">
                    {result.predicted_shelf_life_days != null ? `${result.predicted_shelf_life_days.toFixed(1)} days` : '—'}
                  </p>
                  {result.ci_lo_days != null && (
                    <p className="text-[11px] text-violet-500 mt-1">
                      95% CI: [{result.ci_lo_days.toFixed(1)}, {result.ci_hi_days?.toFixed(1)}] days
                    </p>
                  )}
                </div>

                {result.p_success != null && (
                  <div className={clsx(
                    'rounded-2xl border p-5',
                    result.success ? 'border-green-200 bg-green-50' : 'border-amber-200 bg-amber-50'
                  )}>
                    <p className={clsx(
                      'text-[11px] font-bold uppercase tracking-wider mb-2',
                      result.success ? 'text-green-600' : 'text-amber-600'
                    )}>P(meets target shelf life)</p>
                    <p className={clsx('text-3xl font-black', result.success ? 'text-green-800' : 'text-amber-800')}>
                      {(result.p_success * 100).toFixed(0)}%
                    </p>
                    <p className={clsx('text-[11px] mt-1', result.success ? 'text-green-600' : 'text-amber-600')}>
                      {result.success ? 'Likely to meet target' : 'May not meet target'}
                    </p>
                  </div>
                )}

                {result.expected_spoilage_date && (
                  <div className="col-span-2 rounded-2xl border border-slate-200 bg-slate-50 p-5">
                    <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">Expected spoilage date</p>
                    <p className="text-lg font-bold text-slate-800">{result.expected_spoilage_date}</p>
                  </div>
                )}
              </div>
            )}

            {/* Model provenance */}
            <div className="bg-white rounded-2xl border border-slate-200 px-5 py-3">
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">Source model</p>
              <p className="text-sm text-slate-700 font-medium">{result.model_name}</p>
              {selectedRun && (
                <p className="text-[12px] text-slate-400 mt-0.5">
                  Run #{selectedModel?.training_run_id} · {selectedRun.dataset_name ?? `Dataset #${selectedRun.dataset_id}`} · {new Date(selectedRun.created_at).toLocaleDateString()}
                  {selectedModel?.concordance_index != null && ` · C-index ${selectedModel.concordance_index.toFixed(3)}`}
                </p>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function PredictTab({ projectId }: { projectId: number }) {
  const [models, setModels] = useState<ModelResult[]>([])
  const [runs, setRuns]     = useState<TrainingRunStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [mode, setMode]     = useState<'survival' | 'kinetic' | null>(null)

  useEffect(() => {
    Promise.all([listModels(projectId), listRuns(projectId)])
      .then(([ms, rs]) => {
        setModels(ms)
        setRuns(rs)
        const hasSurvival = ms.some((m) => m.status === 'completed' && m.is_active && m.model_family === 'survival')
        const hasKinetic  = ms.some((m) => m.status === 'completed' && m.is_active && m.model_family === 'kinetic')
        if (hasSurvival) setMode('survival')
        else if (hasKinetic) setMode('kinetic')
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [projectId])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 size={24} className="text-violet-500 animate-spin" />
      </div>
    )
  }

  const survivalModels = models.filter((m) => m.status === 'completed' && m.is_active && m.model_family === 'survival')
  const kineticModels  = models.filter((m) => m.status === 'completed' && m.is_active && m.model_family === 'kinetic')
  const hasAny = survivalModels.length > 0 || kineticModels.length > 0

  if (!hasAny) {
    return (
      <div className="flex flex-col items-center justify-center py-24 space-y-4">
        <div className="w-16 h-16 rounded-2xl bg-violet-100 flex items-center justify-center">
          <FlaskConical size={28} className="text-violet-400" />
        </div>
        <div className="text-center max-w-md">
          <h2 className="text-lg font-bold text-slate-900 mb-1">No trained models yet</h2>
          <p className="text-sm text-slate-500 leading-relaxed">
            Train a <strong>kinetic</strong> dataset to see model fit quality here, or train a
            <strong> survival</strong> dataset (time-to-failure with covariates) to predict shelf life for new formulations.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Mode toggle — only show if both families exist */}
      {survivalModels.length > 0 && kineticModels.length > 0 && (
        <div className="flex items-center gap-1 bg-slate-100 rounded-xl p-1 w-fit">
          <button
            onClick={() => setMode('survival')}
            className={clsx(
              'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all',
              mode === 'survival'
                ? 'bg-white text-violet-700 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            )}
          >
            <Zap size={13} /> Formulation Prediction
            <span className="ml-1 text-[10px] bg-violet-100 text-violet-600 px-1.5 py-0.5 rounded-full font-bold">
              Survival
            </span>
          </button>
          <button
            onClick={() => setMode('kinetic')}
            className={clsx(
              'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all',
              mode === 'kinetic'
                ? 'bg-white text-teal-700 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            )}
          >
            <Activity size={13} /> Model Summary
            <span className="ml-1 text-[10px] bg-teal-100 text-teal-600 px-1.5 py-0.5 rounded-full font-bold">
              Kinetic
            </span>
          </button>
        </div>
      )}

      {mode === 'survival' && survivalModels.length > 0 && (
        <SurvivalPredictPanel projectId={projectId} models={survivalModels} runs={runs} />
      )}

      {mode === 'kinetic' && kineticModels.length > 0 && (
        <KineticModelSummary models={kineticModels} runs={runs} />
      )}

      {/* If only one family, but mode hasn't auto-set yet (edge case) */}
      {!mode && survivalModels.length > 0 && (
        <SurvivalPredictPanel projectId={projectId} models={survivalModels} runs={runs} />
      )}
      {!mode && kineticModels.length === 0 && survivalModels.length === 0 && null}
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function ModelTrainingPage() {
  const { projectId: projectIdStr = '0' } = useParams<{ projectId: string }>()
  const projectId = parseInt(projectIdStr, 10)
  const navigate  = useNavigate()

  const [activeTab, setActiveTab] = useState<Tab>('dataset')

  const handleGuide = (m: ModelDoc) =>
    navigate(`/projects/${projectIdStr}/model-lab/guide/${m.id}`)

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="shrink-0 bg-white border-b border-slate-100 px-8 pt-6 pb-0">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-sm shadow-violet-200">
            <BrainCircuit size={17} className="text-white" />
          </div>
          <div>
            <h1 className="font-bold text-xl text-slate-900">Model Lab</h1>
            <p className="text-[12px] text-slate-400">Train predictive models · Predict shelf life · Compare formulations</p>
          </div>
        </div>

        <div className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={clsx(
                'flex items-center gap-2 px-4 py-2.5 rounded-t-lg text-sm font-medium transition-all border-b-2 -mb-px',
                activeTab === t.id
                  ? 'border-violet-600 text-violet-700 bg-violet-50/50'
                  : 'border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-50'
              )}
            >
              <span className={activeTab === t.id ? 'text-violet-600' : 'text-slate-400'}>{t.icon}</span>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-8 py-7">
        {activeTab === 'dataset' && (
          <DatasetTab onGoToTrain={() => setActiveTab('train')} />
        )}
        {activeTab === 'models' && (
          <ModelsTab projectId={projectId} onGuide={handleGuide} />
        )}
        {activeTab === 'train' && (
          <TrainTab projectId={projectId} onGoToDataset={() => setActiveTab('dataset')} />
        )}
        {activeTab === 'predict' && (
          <PredictTab projectId={projectId} />
        )}
      </div>
    </div>
  )
}
