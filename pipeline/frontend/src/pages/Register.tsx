import { useState, FormEvent, useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Mail, Lock, User, ArrowRight } from 'lucide-react'
import toast from 'react-hot-toast'
import { register as registerRequest } from '../api/auth'
import { errorMessage } from '../api/errors'
import { useAuthStore } from '../store/auth'

function ParticleCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    let animId: number
    const W = canvas.width = canvas.offsetWidth
    const H = canvas.height = canvas.offsetHeight
    type P = { x: number; y: number; vx: number; vy: number; r: number }
    const pts: P[] = Array.from({ length: 55 }, () => ({
      x: Math.random() * W, y: Math.random() * H,
      vx: (Math.random() - 0.5) * 0.3, vy: (Math.random() - 0.5) * 0.3,
      r: Math.random() * 2 + 1,
    }))
    const tick = () => {
      ctx.clearRect(0, 0, W, H)
      for (const p of pts) {
        p.x += p.vx; p.y += p.vy
        if (p.x < 0) p.x = W; if (p.x > W) p.x = 0
        if (p.y < 0) p.y = H; if (p.y > H) p.y = 0
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fillStyle = 'rgba(255,255,255,0.5)'; ctx.fill()
      }
      for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) {
        const dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y
        const d = Math.sqrt(dx * dx + dy * dy)
        if (d < 120) { ctx.beginPath(); ctx.moveTo(pts[i].x, pts[i].y); ctx.lineTo(pts[j].x, pts[j].y); ctx.strokeStyle = `rgba(255,200,210,${(1 - d / 120) * 0.22})`; ctx.lineWidth = 0.7; ctx.stroke() }
      }
      animId = requestAnimationFrame(tick)
    }
    tick()
    return () => cancelAnimationFrame(animId)
  }, [])
  return <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />
}

export default function Register() {
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const { setAuth } = useAuthStore()
  const navigate = useNavigate()

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (password.length < 8) { toast.error('Password must be at least 8 characters'); return }
    setLoading(true)
    try {
      const data = await registerRequest(email, fullName, password)
      setAuth(data.access_token, data.user)
      navigate('/')
    } catch (error) {
      toast.error(errorMessage(error, 'Could not create your account'))
    } finally {
      setLoading(false)
    }
  }

  const field = (
    label: string,
    type: string,
    value: string,
    onChange: (v: string) => void,
    placeholder: string,
    Icon: React.ElementType,
  ) => (
    <div>
      <label className="block text-xs font-semibold text-slate-700 mb-1.5 uppercase tracking-wide">{label}</label>
      <div className="relative">
        <Icon size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
        <input
          type={type}
          className="w-full bg-white border border-slate-200 rounded-xl px-3 py-3 pl-10 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-[#C8102E]/40 focus:border-[#C8102E] transition shadow-sm"
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required
        />
      </div>
    </div>
  )

  return (
    <div className="min-h-screen flex bg-white">
      {/* Left panel */}
      <div className="hidden lg:flex lg:w-[54%] relative overflow-hidden flex-col">
        <div className="absolute inset-0 bg-gradient-to-br from-[#6B0018] via-[#C8102E] to-[#8B0000]" />
        <div className="absolute top-[-20%] right-[-10%] w-[500px] h-[500px] rounded-full bg-white/5 animate-blob1" />
        <div className="absolute bottom-[-10%] left-[-15%] w-[400px] h-[400px] rounded-full bg-white/5 animate-blob2" />
        <ParticleCanvas />
        <div className="relative z-10 flex flex-col h-full p-12">
          <div className="flex items-center gap-3">
            <div className="bg-white rounded-lg p-1.5 shadow-lg">
              <img src="/mcgill.png" alt="McGill" className="h-9 w-auto" />
            </div>
            <div>
              <p className="text-white font-bold text-base leading-tight">McGill University</p>
              <p className="text-white/70 text-xs leading-tight">Faculty of Agricultural & Environmental Sciences</p>
            </div>
          </div>
          <div className="mt-auto mb-auto pt-20">
            <div className="inline-flex items-center gap-2 px-3 py-1 bg-white/15 rounded-full border border-white/25 mb-6">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-white/90 text-xs font-medium">Join the Research Team</span>
            </div>
            <h1 className="text-5xl font-extrabold text-white leading-tight tracking-tight mb-4">
              Create Your<br /><span className="text-white/80">Account</span>
            </h1>
            <p className="text-white/75 text-lg leading-relaxed max-w-md">
              Start collaborating on food preservation research. Upload papers, extract data with AI, and share findings with your team.
            </p>
          </div>
          <p className="text-white/40 text-xs">© 2025 McGill University · Food Science Research Program</p>
        </div>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex flex-col items-center justify-center px-8 py-12 bg-slate-50 relative">
        <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-to-bl from-[#C8102E]/5 to-transparent rounded-bl-full pointer-events-none" />
        <div className="w-full max-w-[380px]">
          {/* Mobile logo */}
          <div className="flex items-center gap-3 mb-8 lg:hidden">
            <div className="bg-[#C8102E] rounded-lg p-1.5">
              <img src="/mcgill.png" alt="McGill" className="h-7 w-auto brightness-0 invert" />
            </div>
            <div>
              <p className="font-bold text-slate-900 text-sm leading-tight">Meat & Cheese Database</p>
              <p className="text-slate-500 text-xs">McGill University</p>
            </div>
          </div>

          <div className="mb-8">
            <h2 className="text-3xl font-extrabold text-slate-900 tracking-tight">Create account</h2>
            <p className="text-slate-500 text-sm mt-1.5">Join the research platform</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {field('Full name', 'text', fullName, setFullName, 'Dr. Jane Smith', User)}
            {field('Email address', 'email', email, setEmail, 'you@university.edu', Mail)}
            {field('Password', 'password', password, setPassword, 'Min. 8 characters', Lock)}
            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 py-3 bg-[#C8102E] hover:bg-[#a60d26] active:bg-[#8B0000] text-white font-semibold rounded-xl transition-all shadow-lg shadow-[#C8102E]/25 disabled:opacity-50 text-sm"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Creating account…
                </span>
              ) : (
                <>Create Account <ArrowRight size={15} /></>
              )}
            </button>
          </form>

          <div className="mt-6 pt-6 border-t border-slate-200 text-center">
            <p className="text-sm text-slate-500">
              Already have an account?{' '}
              <Link to="/login" className="text-[#C8102E] hover:text-[#a60d26] font-semibold transition-colors">
                Sign in
              </Link>
            </p>
          </div>

          <div className="mt-8 flex items-center justify-center gap-2 text-slate-400">
            <div className="h-px bg-slate-200 flex-1" />
            <div className="flex items-center gap-1.5 px-3">
              <img src="/mcgill.png" alt="" className="h-4 w-auto opacity-30" />
              <span className="text-[10px] font-medium">McGill University</span>
            </div>
            <div className="h-px bg-slate-200 flex-1" />
          </div>
        </div>
      </div>
    </div>
  )
}
