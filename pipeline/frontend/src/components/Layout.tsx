import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/auth'
import {
  FlaskConical, LayoutDashboard, LogOut, User, ChevronRight
} from 'lucide-react'

export default function Layout() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top nav */}
      <header className="bg-slate-900 border-b border-slate-800 px-6 h-14 flex items-center justify-between shrink-0">
        <NavLink to="/" className="flex items-center gap-2 font-semibold text-blue-400">
          <FlaskConical size={20} />
          <span>Food Research Platform</span>
        </NavLink>
        <div className="flex items-center gap-4">
          <span className="text-sm text-slate-400 hidden sm:block">
            {user?.full_name}
          </span>
          <button
            onClick={handleLogout}
            className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200 transition-colors"
          >
            <LogOut size={15} />
            <span>Logout</span>
          </button>
        </div>
      </header>

      {/* Page content */}
      <main className="flex-1 container mx-auto max-w-7xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
