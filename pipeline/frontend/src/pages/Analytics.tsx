import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Download, TrendingUp, FileText, CheckCircle, Clock } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, ScatterChart, Scatter,
} from 'recharts'
import toast from 'react-hot-toast'
import { analyticsApi, exportApi } from '../services/api'
import { Analytics as AnalyticsType } from '../types'

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4']

const StatCard = ({ label, value, icon: Icon, color }: { label: string; value: number; icon: any; color: string }) => (
  <div className="card flex items-center gap-4">
    <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
      <Icon size={18} className="text-white" />
    </div>
    <div>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </div>
  </div>
)

export default function Analytics() {
  const { projectId } = useParams<{ projectId: string }>()
  const pid = Number(projectId)
  const [data, setData] = useState<AnalyticsType | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    analyticsApi.get(pid)
      .then(setData)
      .catch(() => toast.error('Failed to load analytics'))
      .finally(() => setLoading(false))
  }, [pid])

  if (loading) return <div className="text-center text-slate-500 py-20">Loading analytics...</div>
  if (!data) return <div className="text-center text-red-400 py-20">Failed to load</div>

  const coverageData = Object.values(data.field_coverage).map((f) => ({
    name: f.label.length > 18 ? f.label.slice(0, 18) + '…' : f.label,
    pct: f.pct,
    filled: f.filled,
  })).sort((a, b) => b.pct - a.pct).slice(0, 15)

  const statusPie = [
    { name: 'Approved', value: data.summary.approved },
    { name: 'Pending', value: data.summary.pending },
    { name: 'Rejected', value: data.summary.rejected },
  ].filter((d) => d.value > 0)

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 justify-between flex-wrap">
        <div className="flex items-center gap-3">
          <Link to={`/projects/${pid}`} className="text-slate-500 hover:text-slate-300"><ArrowLeft size={18} /></Link>
          <h1 className="text-xl font-bold">Analytics</h1>
        </div>
        <button onClick={() => exportApi.excel(pid)} className="btn-secondary text-xs">
          <Download size={13} /> Export Excel
        </button>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Papers" value={data.summary.total_papers} icon={FileText} color="bg-blue-600" />
        <StatCard label="Total Rows" value={data.summary.total_rows} icon={TrendingUp} color="bg-purple-600" />
        <StatCard label="Approved" value={data.summary.approved} icon={CheckCircle} color="bg-green-600" />
        <StatCard label="Pending" value={data.summary.pending} icon={Clock} color="bg-amber-600" />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Row status pie */}
        {statusPie.length > 0 && (
          <div className="card">
            <h3 className="font-semibold mb-4 text-sm text-slate-300">Row Status Distribution</h3>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={statusPie} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label>
                  {statusPie.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Field coverage */}
        {coverageData.length > 0 && (
          <div className="card">
            <h3 className="font-semibold mb-4 text-sm text-slate-300">Field Coverage (%)</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={coverageData} layout="vertical" margin={{ left: 0, right: 16 }}>
                <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11, fill: '#64748b' }} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: '#94a3b8' }} width={100} />
                <Tooltip
                  contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                  formatter={(v: number) => [`${v}%`, 'Coverage']}
                />
                <Bar dataKey="pct" fill="#3b82f6" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Numeric distributions */}
      {Object.keys(data.distributions).length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Object.entries(data.distributions).map(([key, dist], ci) => {
            const histData: { bin: string; count: number }[] = []
            if (dist.values.length > 0) {
              const bins = 10
              const min = dist.min, max = dist.max
              const step = (max - min) / bins || 1
              const counts = Array(bins).fill(0)
              dist.values.forEach((v) => {
                const i = Math.min(Math.floor((v - min) / step), bins - 1)
                counts[i]++
              })
              counts.forEach((c, i) => {
                histData.push({ bin: (min + i * step).toFixed(1), count: c })
              })
            }
            return (
              <div key={key} className="card">
                <h3 className="font-semibold text-sm mb-1 text-slate-300">{dist.label}</h3>
                <div className="text-xs text-slate-500 mb-3">
                  n={dist.count} · min={dist.min} · max={dist.max} · mean={dist.mean}
                </div>
                <ResponsiveContainer width="100%" height={120}>
                  <BarChart data={histData} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
                    <XAxis dataKey="bin" tick={{ fontSize: 9, fill: '#64748b' }} />
                    <YAxis tick={{ fontSize: 9, fill: '#64748b' }} width={24} />
                    <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: 11 }} />
                    <Bar dataKey="count" fill={COLORS[ci % COLORS.length]} radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )
          })}
        </div>
      )}

      {/* Categorical fields */}
      {Object.keys(data.categoricals).length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Object.entries(data.categoricals).map(([key, cat], ci) => (
            <div key={key} className="card">
              <h3 className="font-semibold text-sm mb-4 text-slate-300">{cat.label}</h3>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={cat.data} margin={{ top: 0, right: 8, bottom: 20, left: 0 }}>
                  <XAxis dataKey="value" tick={{ fontSize: 10, fill: '#94a3b8' }} angle={-20} textAnchor="end" />
                  <YAxis tick={{ fontSize: 10, fill: '#64748b' }} width={28} />
                  <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6 }} />
                  <Bar dataKey="count" fill={COLORS[(ci + 2) % COLORS.length]} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ))}
        </div>
      )}

      {/* Papers table */}
      <div className="card p-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-800 font-semibold text-sm">Papers</div>
        <div className="divide-y divide-slate-800">
          {data.papers.map((p) => (
            <div key={p.paper_id} className="flex items-center gap-4 px-5 py-3 text-sm">
              <span className="flex-1 text-slate-300 truncate">{p.name}</span>
              <span className="text-slate-500 text-xs">{p.page_count} pages</span>
              <span className="text-slate-400">{p.row_count} rows</span>
              <span className={`text-xs px-2 py-0.5 rounded border ${
                p.status === 'extracted' ? 'bg-purple-900/40 text-purple-300 border-purple-800' :
                p.status === 'error' ? 'bg-red-950 text-red-400 border-red-900' :
                'bg-slate-800 text-slate-400 border-slate-700'
              }`}>{p.status}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
