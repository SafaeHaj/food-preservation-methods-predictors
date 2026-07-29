/**
 * Model Lab — the processed dataset, flattened from the scientific schema for modelling.
 *
 * The builder behind this is not written yet (`processing/app/services/dataset_builder.py`
 * documents the mapping and the open questions), so the page's job right now is to show
 * honestly where a project stands: what it has extracted, whether its indicators carry the
 * thresholds a survival label needs, and what shape the dataset will take.
 *
 * It replaces a Model Lab built around uploading a CSV and training against it — a second
 * ingestion path beside the one the whole pipeline exists to run.
 */

import { useParams } from 'react-router-dom'
import { Link } from 'react-router-dom'
import {
  AlertCircle, Beaker, Database, FlaskConical, Gauge, Loader2, Play, Ruler, Table2,
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

import { useBuildDataset, useDataset } from '../../api/dataset'
import { errorMessage } from '../../api/errors'
import { keys } from '../../api/keys'
import { useJobStream } from '../../hooks/useJobStream'
import type { DatasetSource } from '../../api/dataset'

function SourceTile({
  icon, label, value, tone = 'text-slate-900',
}: { icon: React.ReactNode; label: string; value: number; tone?: string }) {
  return (
    <div className="stat-card">
      <div className="stat-icon bg-slate-50">{icon}</div>
      <div>
        <div className={clsx('text-2xl font-bold', tone)}>{value}</div>
        <div className="text-xs text-slate-500 mt-0.5">{label}</div>
      </div>
    </div>
  )
}

function SourceTiles({ source }: { source: DatasetSource }) {
  const missingThresholds = source.indicators - source.indicators_with_threshold
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <SourceTile
        icon={<FlaskConical size={18} className="text-blue-500" />}
        label="Experiments" value={source.experiments}
      />
      <SourceTile
        icon={<Table2 size={18} className="text-violet-500" />}
        label="Measurements" value={source.measurements}
      />
      <SourceTile
        icon={<Beaker size={18} className="text-amber-500" />}
        label="Ingredients" value={source.ingredients}
      />
      <SourceTile
        icon={<Gauge size={18} className="text-emerald-500" />}
        label="Indicators with a threshold"
        value={source.indicators_with_threshold}
        tone={
          source.indicators > 0 && missingThresholds > 0
            ? 'text-amber-600'
            : 'text-slate-900'
        }
      />
    </div>
  )
}

export default function ModelLabPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const pid = Number(projectId)

  const { data: dataset, isLoading } = useDataset(pid)
  const build = useBuildDataset(pid)

  const { isRunning, progress } = useJobStream(build.data?.job_id ?? null, {
    invalidateOnComplete: [keys.dataset.all(pid)],
    onError: (message) => toast.error(`Dataset build failed: ${message}`),
  })

  const handleBuild = () =>
    build
      .mutateAsync()
      .catch((error) => toast.error(errorMessage(error, 'Could not start the build')))

  const source = dataset?.source
  const missingThresholds =
    source ? source.indicators - source.indicators_with_threshold : 0
  const blocked =
    !source || source.experiments === 0 || source.indicators_with_threshold === 0

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start gap-4 justify-between">
        <div>
          <h1 className="page-title">Model Lab</h1>
          <p className="muted mt-1">
            The scientific schema flattened into one row per experiment and day — the shape
            the prediction engines train on.
          </p>
        </div>
        <button
          onClick={handleBuild}
          disabled={build.isPending || isRunning || blocked}
          className="btn-primary"
        >
          {build.isPending || isRunning
            ? <><Loader2 size={14} className="animate-spin" /> Building…</>
            : <><Play size={14} /> Build dataset</>}
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-slate-400 py-8 text-sm">
          <Loader2 size={14} className="animate-spin" /> Loading…
        </div>
      ) : !source ? (
        <p className="text-sm text-slate-400">This dataset could not be loaded.</p>
      ) : (
        <>
          <SourceTiles source={source} />

          {isRunning && progress?.current_step && (
            <p className="text-xs text-blue-600 flex items-center gap-1.5">
              <Loader2 size={11} className="animate-spin" /> {progress.current_step}
            </p>
          )}

          {source.experiments === 0 ? (
            <div className="flex items-start gap-2 text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2.5">
              <AlertCircle size={13} className="text-slate-400 shrink-0 mt-0.5" />
              <span>
                Nothing has been extracted yet. Upload papers and run them through the
                pipeline first — the dataset is built from what comes out of it.
              </span>
            </div>
          ) : missingThresholds > 0 && (
            <div className="flex items-start gap-2 text-xs text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2.5">
              <Ruler size={13} className="text-amber-500 shrink-0 mt-0.5" />
              <span>
                {missingThresholds} indicator{missingThresholds !== 1 ? 's have' : ' has'} no
                threshold. Shelf life is the day an indicator crosses its limit, so those
                measurements cannot be labelled — set the limits in the{' '}
                <Link
                  to={`/projects/${pid}/database`}
                  className="font-semibold underline underline-offset-2"
                >
                  scientific database
                </Link>.
              </span>
            </div>
          )}

          {/* ── The dataset itself ─────────────────────────────────────────── */}
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between gap-3">
              <div>
                <h2 className="section-title">Dataset</h2>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  {dataset.row_count > 0
                    ? `${dataset.row_count} rows × ${dataset.columns.length} columns`
                    : `${dataset.columns.length} planned columns, no rows yet`}
                </p>
              </div>
              {dataset.status === 'not_implemented' && (
                <span className="text-[10px] font-semibold text-slate-500 bg-slate-100 px-2 py-1 rounded-full shrink-0">
                  Builder not implemented
                </span>
              )}
            </div>

            {dataset.rows.length === 0 ? (
              <div className="px-5 py-10 text-center">
                <Database size={32} strokeWidth={1} className="text-slate-200 mx-auto mb-3" />
                <p className="text-sm text-slate-500 max-w-lg mx-auto">
                  The builder that flattens experiments, ingredient concentrations and
                  day-by-day measurements into training rows has not been written yet.
                </p>
                <p className="text-[11px] text-slate-400 mt-3">
                  Planned columns:{' '}
                  <span className="font-mono">{dataset.columns.join(', ')}</span>, plus one
                  per ingredient and one per indicator.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm" style={{ fontVariantNumeric: 'tabular-nums' }}>
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      {dataset.columns.map((column) => (
                        <th
                          key={column}
                          className="px-3 py-2 text-left font-medium text-slate-600 whitespace-nowrap"
                        >
                          {column}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {dataset.rows.map((row, index) => (
                      <tr key={index} className="hover:bg-slate-50">
                        {dataset.columns.map((column) => (
                          <td key={column} className="px-3 py-1.5 text-slate-700 whitespace-nowrap">
                            {row[column] == null ? (
                              <span className="text-slate-300">—</span>
                            ) : (
                              String(row[column])
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
