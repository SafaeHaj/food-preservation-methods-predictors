import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/auth'
import { LogOut, User, ChevronDown } from 'lucide-react'
import { useState } from 'react'

export default function Layout() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const [userMenuOpen, setUserMenuOpen] = useState(false)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      {/* Top nav */}
      <header className="bg-white border-b border-slate-200 shadow-sm sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          {/* Logo */}
          <NavLink to="/" className="flex items-center gap-3 group">
            <div className="bg-white rounded-md p-1 shadow-sm border border-slate-100 group-hover:shadow-md transition-shadow">
              <img src="/mcgill.png" alt="McGill" className="h-7 w-auto" />
            </div>
            <div className="hidden sm:block">
              <span className="font-bold text-slate-900 text-sm">Meat & Cheese</span>
              <span className="text-[#C8102E] font-bold text-sm"> Database</span>
            </div>
          </NavLink>

          {/* User menu */}
          <div className="relative">
            <button
              onClick={() => setUserMenuOpen(!userMenuOpen)}
              className="flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-slate-50 transition-colors"
            >
              <div
                className="w-7 h-7 rounded-full flex items-center justify-center text-white text-[11px] font-bold shadow-sm"
                style={{ background: 'linear-gradient(135deg, #C8102E, #8B0000)' }}
              >
                {user?.full_name?.charAt(0)?.toUpperCase() ?? 'U'}
              </div>
              <span className="text-sm font-medium text-slate-700 hidden sm:block">
                {user?.full_name}
              </span>
              <ChevronDown size={14} className="text-slate-400" />
            </button>

            {userMenuOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setUserMenuOpen(false)} />
                <div className="absolute right-0 top-full mt-1.5 w-52 bg-white border border-slate-200 rounded-xl shadow-lg z-20 py-1.5 overflow-hidden">
                  <div className="px-3 py-2 border-b border-slate-100 mb-1">
                    <p className="text-xs font-semibold text-slate-900 truncate">{user?.full_name}</p>
                    <p className="text-xs text-slate-500 truncate">{user?.email}</p>
                  </div>
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50 transition-colors"
                  >
                    <LogOut size={14} />
                    Sign out
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Dashboard content */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
