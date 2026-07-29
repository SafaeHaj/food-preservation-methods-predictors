/**
 * Prediction — shelf-life models trained on the processed dataset.
 *
 * The engines live in the prediction service (Weibull-AFT, random survival forests,
 * gradient-boosted survival); the processing service holds the seam to them. What is
 * missing is the dataset in between, so this page reports the project's readiness rather
 * than offering a train button that would have nothing to train on.
 *
 * The blocking condition is worth stating plainly, because it is the one the user can fix:
 * shelf life is the day an indicator crosses its threshold, so a project with no thresholds
 * has no labels no matter how many papers it has extracted.
 */

import { Link, useParams } from 'react-router-dom'
import { Brain, CheckCircle2, ChevronRight, Circle, Loader2 } from 'lucide-react'
import clsx from 'clsx'

import { usePredictionStatus } from '../../api/dataset'

/** The chain a project has to complete before anything can be trained. */
function Readiness({
  experiments, thresholds, datasetReady,
}: { experiments: number; thresholds: number; datasetReady: boolean }) {
  const steps = [
    {
      label: 'Papers extracted into the scientific schema',
      done: experiments > 0,
      detail: `${experiments} experiment${experiments !== 1 ? 's' : ''}`,
    },
    {
      label: 'Indicator thresholds set',
      done: thresholds > 0,
      detail: `${thresholds} indicator${thresholds !== 1 ? 's' : ''} can be labelled`,
    },
    {
      label: 'Dataset built',
      done: datasetReady,
      detail: datasetReady ? 'Ready' : 'The builder is not implemented yet',
    },
  ]

  return (
    <ol className="space-y-3">
      {steps.map((step) => (
        <li key={step.label} className="flex items-start gap-2.5">
          {step.done
            ? <CheckCircle2 size={15} className="text-emerald-500 shrink-0 mt-0.5" />
            : <Circle size={15} className="text-slate-200 shrink-0 mt-0.5" />}
          <div className="min-w-0">
            <p className={clsx(
              'text-sm',
              step.done ? 'text-slate-700' : 'text-slate-400',
            )}>
              {step.label}
            </p>
            <p className="text-[11px] text-slate-400">{step.detail}</p>
          </div>
        </li>
      ))}
    </ol>
  )
}

export default function PredictionPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const pid = Number(projectId)

  const { data: status, isLoading } = usePredictionStatus(pid)

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-slate-400 py-8 text-sm">
        <Loader2 size={14} className="animate-spin" /> Loading…
      </div>
    )
  }

  if (!status) {
    return <p className="text-sm text-slate-400">This page could not be loaded.</p>
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="page-title">Prediction</h1>
        <p className="muted mt-1">
          Shelf-life models fitted to this project's data, and predictions for new
          formulations.
        </p>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-5 space-y-5">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 bg-slate-50 rounded-lg flex items-center justify-center shrink-0">
            <Brain size={18} className="text-slate-400" />
          </div>
          <div className="min-w-0">
            <h2 className="section-title">Not available yet</h2>
            <p className="text-xs text-slate-500 mt-1">{status.reason}</p>
          </div>
        </div>

        <Readiness
          experiments={status.source.experiments}
          thresholds={status.source.indicators_with_threshold}
          datasetReady={false}
        />

        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Link to={`/projects/${pid}/database`} className="btn-secondary text-xs">
            Scientific database <ChevronRight size={11} />
          </Link>
          <Link to={`/projects/${pid}/model-lab`} className="btn-secondary text-xs">
            Model Lab <ChevronRight size={11} />
          </Link>
        </div>
      </div>

      {status.engines.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-5">
          <h2 className="section-title">Engines</h2>
          <p className="text-[11px] text-slate-400 mt-0.5 mb-3">
            Survival models the prediction service exposes. Censoring is the point: most
            studies end before every sample has spoiled, so the last observed day is a lower
            bound on shelf life, not the answer.
          </p>
          <div className="flex flex-wrap gap-2">
            {status.engines.map((engine) => (
              <span
                key={engine}
                className="text-[11px] font-mono text-slate-600 bg-slate-100 px-2 py-1 rounded-md"
              >
                {engine}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
