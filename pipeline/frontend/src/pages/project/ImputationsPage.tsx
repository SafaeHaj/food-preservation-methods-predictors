import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useImputations, useReviewImputation } from '../../api/canonical'
import { errorMessage } from '../../api/errors'
import { CheckCircle, XCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'

const APPLICABILITY_COLORS: Record<string, string> = {
  green: 'text-green-700 bg-green-50',
  yellow: 'text-yellow-700 bg-yellow-50',
  red: 'text-red-700 bg-red-50',
}

const DECISION_COLORS: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-600',
  accepted: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
  superseded: 'bg-gray-100 text-gray-400',
}

export default function ImputationsPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [decisionFilter, setDecisionFilter] = useState('pending')

  const { data: proposals = [], isLoading: loading } = useImputations(Number(projectId), {
    reviewer_decision: decisionFilter || undefined,
  })
  // The mutation invalidates the list itself, so there is no manual reload here — and no
  // window in which the list still shows a proposal that has already been decided.
  const reviewImputation = useReviewImputation(Number(projectId))

  const handleReview = async (id: number, decision: 'accepted' | 'rejected') => {
    const note = decision === 'rejected'
      ? window.prompt('Reason for rejection (optional):') ?? undefined
      : undefined
    try {
      await reviewImputation.mutateAsync({ id, decision, note })
      toast.success(decision === 'accepted' ? 'Proposal accepted' : 'Proposal rejected')
    } catch (error) {
      toast.error(errorMessage(error, 'Could not record the decision'))
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Imputation Proposals</h1>
        <div className="flex gap-2">
          <select className="border border-gray-300 rounded px-2 py-1 text-sm" value={decisionFilter}
            onChange={(e) => setDecisionFilter(e.target.value)}>
            <option value="">All</option>
            <option value="pending">Pending</option>
            <option value="accepted">Accepted</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
      </div>

      <p className="text-sm text-gray-500 mb-4">
        Imputed values are proposals only — they never overwrite observed data until explicitly accepted.
      </p>

      {loading ? <p className="text-sm text-gray-500">Loading…</p> : proposals.length === 0 ? (
        <div className="text-center py-12 text-gray-400">No imputation proposals found.</div>
      ) : (
        <div className="space-y-2">
          {proposals.map((p) => (
            <div key={p.id} className="bg-white border border-gray-200 rounded-lg p-4 flex items-start gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-gray-900">#{p.id}</span>
                  {p.applicability_status && (
                    <span className={clsx('px-2 py-0.5 rounded-full text-xs font-medium', APPLICABILITY_COLORS[p.applicability_status])}>
                      {p.applicability_status}
                    </span>
                  )}
                  <span className={clsx('px-2 py-0.5 rounded-full text-xs font-medium', DECISION_COLORS[p.reviewer_decision ?? 'pending'])}>
                    {p.reviewer_decision ?? 'pending'}
                  </span>
                </div>
                <p className="text-sm text-gray-600 mt-1">
                  {p.target_measurement_type ?? 'unknown type'}
                  {' at t='}{p.target_time_days != null ? `${p.target_time_days} days` : '?'}
                  {' → '}<span className="font-mono font-semibold">{p.predicted_value?.toFixed(3) ?? '?'}</span>
                  {p.lower_bound != null ? ` [${p.lower_bound.toFixed(2)}, ${p.upper_bound?.toFixed(2)}]` : ''}
                </p>
                <p className="text-xs text-gray-400 mt-0.5">
                  Model: {p.model_name ?? '—'} · {p.is_interpolation ? 'interpolation' : `extrapolation +${p.extrapolation_days}d`}
                  {p.n_points_used != null ? ` · ${p.n_points_used} points used` : ''}
                  {p.cross_validation_mae != null ? ` · LOO MAE: ${p.cross_validation_mae.toFixed(3)}` : ''}
                </p>
                {p.applicability_reasons.length > 0 && (
                  <p className="text-xs text-orange-600 mt-1">{p.applicability_reasons.join('; ')}</p>
                )}
              </div>
              {p.reviewer_decision === 'pending' && (
                <div className="flex gap-1 shrink-0">
                  <button onClick={() => handleReview(p.id, 'accepted')} className="text-green-600 hover:text-green-800 p-1" title="Accept">
                    <CheckCircle size={18} />
                  </button>
                  <button onClick={() => handleReview(p.id, 'rejected')} className="text-red-500 hover:text-red-700 p-1" title="Reject">
                    <XCircle size={18} />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
