import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { auditApi } from '../../services/api'
import type { AuditEvent } from '../../types'
import { RefreshCw, ChevronDown, ChevronUp } from 'lucide-react'

const ACTION_COLORS: Record<string, string> = {
  create: 'text-green-700 bg-green-50',
  update: 'text-blue-700 bg-blue-50',
  delete: 'text-red-700 bg-red-50',
  approve: 'text-emerald-700 bg-emerald-50',
  reject: 'text-orange-700 bg-orange-50',
  normalize: 'text-purple-700 bg-purple-50',
  impute: 'text-indigo-700 bg-indigo-50',
  export: 'text-gray-700 bg-gray-100',
}

export default function AuditHistoryPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [entityTypeFilter, setEntityTypeFilter] = useState('')
  const [actionFilter, setActionFilter] = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const load = () => {
    if (!projectId) return
    setLoading(true)
    auditApi.list({
      project_id: Number(projectId),
      entity_type: entityTypeFilter || undefined,
      action: actionFilter || undefined,
      limit: 100,
    }).then(setEvents).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [projectId, entityTypeFilter, actionFilter])

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Audit History</h1>
        <div className="flex gap-2">
          <select className="border border-gray-300 rounded px-2 py-1 text-sm" value={entityTypeFilter}
            onChange={(e) => setEntityTypeFilter(e.target.value)}>
            <option value="">All entities</option>
            {['study', 'experiment', 'treatment_arm', 'observation'].map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <select className="border border-gray-300 rounded px-2 py-1 text-sm" value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}>
            <option value="">All actions</option>
            {['create', 'update', 'delete', 'approve', 'reject', 'normalize', 'impute', 'export'].map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
          <button onClick={load} className="flex items-center gap-1 text-sm text-gray-600 border border-gray-300 rounded px-2 py-1">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {loading ? <p className="text-sm text-gray-500">Loading…</p> : events.length === 0 ? (
        <div className="text-center py-12 text-gray-400">No audit events yet.</div>
      ) : (
        <div className="space-y-1">
          {events.map((e) => (
            <div key={e.id} className="bg-white border border-gray-200 rounded-lg">
              <button
                className="w-full flex items-center gap-3 px-4 py-3 text-sm text-left"
                onClick={() => setExpandedId(expandedId === e.id ? null : e.id)}
              >
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${ACTION_COLORS[e.action] ?? 'bg-gray-100 text-gray-600'}`}>
                  {e.action}
                </span>
                <span className="text-gray-500">{e.entity_type} #{e.entity_id}</span>
                <span className="flex-1 text-gray-400 text-xs">
                  {e.reason ? `"${e.reason}"` : ''}
                </span>
                <span className="text-gray-400 text-xs">{new Date(e.created_at).toLocaleString()}</span>
                {e.diff && Object.keys(e.diff).length > 0 && (
                  expandedId === e.id ? <ChevronUp size={14} className="text-gray-400" /> : <ChevronDown size={14} className="text-gray-400" />
                )}
              </button>
              {expandedId === e.id && e.diff && Object.keys(e.diff).length > 0 && (
                <div className="border-t border-gray-100 px-4 py-3">
                  <table className="text-xs w-full">
                    <thead>
                      <tr className="text-gray-500">
                        <th className="text-left py-1 font-medium">Field</th>
                        <th className="text-left py-1 font-medium">Before</th>
                        <th className="text-left py-1 font-medium">After</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(e.diff).map(([field, { before, after }]) => (
                        <tr key={field} className="border-t border-gray-50">
                          <td className="py-1 font-mono text-gray-600 pr-4">{field}</td>
                          <td className="py-1 text-red-600 pr-4">{String(before ?? '—')}</td>
                          <td className="py-1 text-green-700">{String(after ?? '—')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
