import { NavLink, useParams, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Upload, Cpu, ShieldCheck, ClipboardList,
  Database, FlaskConical, Activity, GitBranch, Download, Users, Settings,
  History, LogOut, ChevronRight, Table2,
} from 'lucide-react'
import clsx from 'clsx'
import { useAuthStore } from '../store/auth'

// "Extraction Review" pointed at the legacy flat-row review screen, which was removed
// along with the extraction path that produced its data. Curation now happens on the
// Validation screen (before the LLM runs) and in the Scientific Database (after).
const EXTRACTION_NAV = [
  { to: '',          end: true, label: 'Dashboard',      Icon: LayoutDashboard },
  { to: 'upload',              label: 'Upload Papers',   Icon: Upload },
  { to: 'jobs',                label: 'Extraction Jobs', Icon: Cpu },
  { to: 'validation',          label: 'Validation',      Icon: ShieldCheck },
  { to: 'extracted',           label: 'Extracted Data',  Icon: Table2 },
]

const DATABASE_NAV = [
  { to: 'studies',      label: 'Studies',             Icon: ClipboardList },
  { to: 'dataset',      label: 'Scientific Database', Icon: Database },
  { to: 'experiments',  label: 'Experiments',         Icon: FlaskConical },
  { to: 'trajectories', label: 'Trajectories',        Icon: Activity },
]

const MODELS_NAV = [
  { to: 'model-lab',  label: 'Kinetic Models',   Icon: GitBranch },
  { to: 'thresholds', label: 'Shelf-Life Models', Icon: Activity },
  { to: 'export',     label: 'Model Registry',    Icon: Download },
]

const ADMIN_NAV = [
  { to: 'team',     label: 'Team',     Icon: Users },
  { to: 'settings', label: 'Settings', Icon: Settings },
  { to: 'audit',    label: 'Audit Log', Icon: History },
]

function SectionLabel({ label }: { label: string }) {
  return (
    <p className="px-3 pt-5 pb-1 text-[9.5px] font-bold uppercase tracking-widest text-slate-400 select-none">
      {label}
    </p>
  )
}

interface NavItemProps { to: string; label: string; Icon: React.ElementType; end?: boolean }

function NavItem({ to, label, Icon, end }: NavItemProps) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        clsx(
          'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all duration-150',
          isActive
            ? 'bg-[#C8102E] text-white font-semibold shadow-sm'
            : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100',
        )
      }
    >
      {({ isActive }) => (
        <>
          <Icon
            size={14}
            className={clsx('shrink-0', isActive ? 'text-white' : 'text-slate-400')}
          />
          <span className="truncate flex-1 text-[13px]">{label}</span>
          {isActive && <ChevronRight size={10} className="shrink-0 opacity-60" />}
        </>
      )}
    </NavLink>
  )
}

export default function ProjectSidebar() {
  const { projectId } = useParams<{ projectId: string }>()
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const base = `/projects/${projectId}`

  return (
    <aside className="w-60 shrink-0 bg-white h-full flex flex-col overflow-hidden border-r border-slate-200 shadow-sm">

      {/* ── Brand ─────────────────────────────────────────────────────────── */}
      <div className="px-4 pt-5 pb-4 border-b border-slate-100 shrink-0">
        <div className="flex items-center gap-2.5 mb-3">
          <div className="bg-white rounded-md p-1 shadow-sm border border-slate-100">
            <img src="/mcgill.png" alt="McGill" className="h-7 w-auto" />
          </div>
          <div className="min-w-0">
            <p className="text-[11px] font-bold text-slate-800 leading-tight">McGill University</p>
            <p className="text-[9.5px] text-slate-400 leading-tight">Agricultural Sciences</p>
          </div>
        </div>
        {/* Project pill */}
        <div className="px-2.5 py-1.5 bg-[#C8102E]/8 rounded-lg border border-[#C8102E]/15">
          <p className="text-[11.5px] font-bold text-[#C8102E] truncate leading-tight">Meat & Cheese DB</p>
          <p className="text-[9.5px] text-[#C8102E]/60 leading-tight mt-0.5">Research Platform</p>
        </div>
      </div>

      {/* ── Nav ───────────────────────────────────────────────────────────── */}
      <nav className="flex-1 overflow-y-auto px-3 py-2 scrollbar-none">
        <SectionLabel label="Extraction Pipeline" />
        <div className="space-y-0.5">
          {EXTRACTION_NAV.map(({ to, end, label, Icon }) => (
            <NavItem
              key={label}
              to={end ? base : `${base}/${to}`}
              label={label}
              Icon={Icon}
              end={end}
            />
          ))}
        </div>

        <SectionLabel label="Scientific Database" />
        <div className="space-y-0.5">
          {DATABASE_NAV.map(({ to, label, Icon }) => (
            <NavItem key={label} to={`${base}/${to}`} label={label} Icon={Icon} />
          ))}
        </div>

        <SectionLabel label="Analysis & Models" />
        <div className="space-y-0.5">
          {MODELS_NAV.map(({ to, label, Icon }) => (
            <NavItem key={label} to={`${base}/${to}`} label={label} Icon={Icon} />
          ))}
        </div>

        <SectionLabel label="Administration" />
        <div className="space-y-0.5">
          {ADMIN_NAV.map(({ to, label, Icon }) => (
            <NavItem key={label} to={`${base}/${to}`} label={label} Icon={Icon} />
          ))}
        </div>
      </nav>

      {/* ── User strip ────────────────────────────────────────────────────── */}
      <div className="shrink-0 border-t border-slate-100 px-3 py-3">
        <div className="flex items-center gap-2.5">
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-white text-[11px] font-bold shadow-sm"
            style={{ background: 'linear-gradient(135deg, #C8102E, #8B0000)' }}
          >
            {user?.full_name?.charAt(0)?.toUpperCase() ?? 'U'}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold text-slate-800 truncate leading-tight">{user?.full_name}</p>
            <p className="text-[10px] text-slate-400 truncate leading-tight">{user?.email}</p>
          </div>
          <button
            onClick={() => { logout(); navigate('/login') }}
            title="Sign out"
            className="p-1.5 text-slate-400 hover:text-[#C8102E] hover:bg-red-50 rounded-lg transition-colors"
          >
            <LogOut size={13} />
          </button>
        </div>
      </div>
    </aside>
  )
}
