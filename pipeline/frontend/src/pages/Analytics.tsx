import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Download, TrendingUp, FileText, CheckCircle, Clock, AlertCircle } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts'
import toast from 'react-hot-toast'
import { analyticsApi, exportApi } from '../services/api'
import { Analytics as AnalyticsType } from '../types'

const COLORS = ['#2563EB', '#059669', '#D97706', '#DC2626', '#7C3AED', '#0891B2']

const TOOLTIP_STYLE = {
  background: '#fff',
  border: '1px solid #E2E8F0',
  borderRadius: 10,
  boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
  fontSize: 12,
  color: '#0F172A',
}

const StatCard = ({ label, value, icon: Icon, color, textColor }: {
  label: string; value: number; icon: any; color: string; textColor: string
}) => (
  <div className="stat-card">
    <div className={`stat-icon ${color}`}>
      <Icon size={18} className={textColor} />
    </div>
    <div>
      <div className="text-2xl font-bold text-slate-900">{value}</div>
      <div className="text-xs text-slate-500 mt-0.5">{label}</div>
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

  if (loading) return (
    <div className="flex items-center justify-center py-24">
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-sm text-slate-500">Loading analytics…</p>
      </div>
    </div>
  )

  if (!data) return (
    <div className="text-center py-24">
      <AlertCircle size={32} className="text-red-400 mx-auto mb-3" />
      <p className="text-slate-600">Failed to load analytics</p>
    </div>
  )

  const coverageData = Object.values(data.field_coverage)
    .map((f) => ({
      name: f.label.length > 20 ? f.label.slice(0, 20) + '…' : f.label,
      pct: f.pct,
    }))
    .sort((a, b) => b.pct - a.pct)
    .slice(0, 15)

  const statusPie = [
    { name: 'Approved', value: data.summary.approved },
    { name: 'Pending', value: data.summary.pending },
    { name: 'Rejected', value: data.summary.rejected },
  ].filter((d) => d.value > 0)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3 justify-between flex-wrap">
        <div className="flex items-center gap-3">
          <Link to={`/projects/${pid}`} className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors">
            <ArrowLeft size={18} />
          </Link>
          <div>
            <h1 className="page-title">Analytics</h1>
            <p className="muted">Data quality & distribution overview</p>
          </div>
        </div>
        <button
          onClick={() => exportApi.excel(pid)}
          className="btn-primary"
        >
          <Download size={14} /> Export Excel
        </button>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Papers" value={data.summary.total_papers} icon={FileText} color="bg-blue-50" textColor="text-blue-600" />
        <StatCard label="Total Rows" value={data.summary.total_rows} icon={TrendingUp} color="bg-violet-50" textColor="text-violet-600" />
        <StatCard label="Approved" value={data.summary.approved} icon={CheckCircle} color="bg-emerald-50" textColor="text-emerald-600" />
        <StatCard label="Pending Review" value={data.summary.pending} icon={Clock} color="bg-amber-50" textColor="text-amber-600" />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {statusPie.length > 0 && (
          <div className="card">
            <h3 className="section-title mb-5">Row Status Distribution</h3>
            <ResponsiveContainer width="100%" height={230}>
              <PieChart>
                <Pie data={statusPie} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={85} innerRadius={45} paddingAngle={3}>
                  {statusPie.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}

        {coverageData.length > 0 && (
          <div className="card">
            <h3 className="section-title mb-5">Field Coverage (%)</h3>
            <ResponsiveContainer width="100%" height={230}>
              <BarChart data={coverageData} layout="vertical" margin={{ left: 0, right: 20 }}>
                <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11, fill: '#94A3B8' }} tickLine={false} axisLine={false} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: '#64748B' }} width={110} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => [`${v}%`, 'Coverage']} />
                <Bar dataKey="pct" fill="#2563EB" radius={4} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Numeric distributions */}
      {Object.keys(data.distributions).length > 0 && (
        <div>
          <h2 className="section-title mb-4">Numeric Distributions</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {Object.entries(data.distributions).map(([key, dist], ci) => {
              const histData: { bin: string; count: number }[] = []
              if (dist.values.length > 0) {
                const bins = 10
                const step = (dist.max - dist.min) / bins || 1
                const counts = Array(bins).fill(0)
                dist.values.forEach((v) => {
                  const i = Math.min(Math.floor((v - dist.min) / step), bins - 1)
                  counts[i]++
                })
                counts.forEach((c, i) => {
                  histData.push({ bin: (dist.min + i * step).toFixed(1), count: c })
                })
              }
              return (
                <div key={key} className="card">
                  <h3 className="text-sm font-semibold text-slate-900 mb-0.5">{dist.label}</h3>
                  <p className="text-xs text-slate-400 mb-4">
                    n={dist.count} · min={dist.min} · max={dist.max} · mean={dist.mean}
                  </p>
                  <ResponsiveContainer width="100%" height={110}>
                    <BarChart data={histData} margin={{ top: 0, right: 0, bottom: 0, left: -10 }}>
                      <XAxis dataKey="bin" tick={{ fontSize: 9, fill: '#94A3B8' }} tickLine={false} axisLine={false} />
                      <YAxis tick={{ fontSize: 9, fill: '#94A3B8' }} width={24} tickLine={false} axisLine={false} />
                      <Tooltip contentStyle={TOOLTIP_STYLE} />
                      <Bar dataKey="count" fill={COLORS[ci % COLORS.length]} radius={3} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Categorical fields */}
      {Object.keys(data.categoricals).length > 0 && (
        <div>
          <h2 className="section-title mb-4">Categorical Distributions</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {Object.entries(data.categoricals).map(([key, cat], ci) => (
              <div key={key} className="card">
                <h3 className="text-sm font-semibold text-slate-900 mb-4">{cat.label}</h3>
                <ResponsiveContainer width="100%" height={170}>
                  <BarChart data={cat.data} margin={{ top: 0, right: 8, bottom: 24, left: -10 }}>
                    <XAxis dataKey="value" tick={{ fontSize: 10, fill: '#64748B' }} angle={-15} textAnchor="end" tickLine={false} axisLine={false} />
                    <YAxis tick={{ fontSize: 10, fill: '#94A3B8' }} width={28} tickLine={false} axisLine={false} />
                    <Tooltip contentStyle={TOOLTIP_STYLE} />
                    <Bar dataKey="count" fill={COLORS[(ci + 2) % COLORS.length]} radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Papers table */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100">
          <h2 className="section-title">Papers Overview</h2>
        </div>
        <div className="divide-y divide-slate-100">
          {data.papers.map((p) => (
            <div key={p.paper_id} className="flex items-center gap-4 px-6 py-3.5 hover:bg-slate-50 transition-colors">
              <div className="w-7 h-7 bg-blue-50 rounded-lg flex items-center justify-center shrink-0">
                <FileText size={13} className="text-blue-500" />
              </div>
              <span className="flex-1 text-sm text-slate-900 truncate font-medium">{p.name}</span>
              <span className="text-xs text-slate-400">{p.page_count} pages</span>
              <span className="text-sm font-semibold text-slate-700">{p.row_count} rows</span>
              <span className={`text-xs px-2.5 py-0.5 rounded-full font-semibold border ${
                p.status === 'extracted' ? 'bg-violet-50 text-violet-700 border-violet-200' :
                p.status === 'error' ? 'bg-red-50 text-red-600 border-red-200' :
                'bg-slate-50 text-slate-500 border-slate-200'
              }`}>{p.status}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
